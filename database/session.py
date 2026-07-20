"""Database setup and repositories."""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from database.models import (
    Base,
    CalculationPointRow,
    CalculationRunRow,
    ConversationRow,
    EvidenceRecordRow,
    ExportRecordRow,
    MessageRow,
    ParameterSetRow,
    TaskRow,
    ValidationReportRow,
)
from schemas.domain import CalculationEnvelope, ParameterSet, RunRecord


def create_database_engine(url: str | None = None) -> Engine:
    database_url: str = url if url is not None else (os.environ.get("DATABASE_URL") or "sqlite:///./thermoequi.db")
    arguments = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=arguments)


engine = create_database_engine()


def initialize_database(target: Engine = engine) -> None:
    Base.metadata.create_all(target)


def session_scope(target: Engine = engine) -> Iterator[Session]:
    with Session(target) as session:
        yield session


class Repository:
    def __init__(self, target: Engine = engine) -> None:
        self.engine = target

    def save_chat(self, conversation_id: str, user_message: str, response_payload: dict[str, object]) -> None:
        with Session(self.engine) as session:
            conversation = session.get(ConversationRow, conversation_id)
            if conversation is None:
                session.add(ConversationRow(id=conversation_id))
            session.add(
                MessageRow(
                    id=str(uuid4()),
                    conversation_id=conversation_id,
                    role="user",
                    content=user_message,
                )
            )
            session.add(
                MessageRow(
                    id=str(uuid4()),
                    conversation_id=conversation_id,
                    role="assistant",
                    content=str(response_payload.get("answer", "")),
                    structured=response_payload,
                )
            )
            task = response_payload.get("task")
            if isinstance(task, dict):
                session.merge(TaskRow(id=str(task["task_id"]), conversation_id=conversation_id, manifest=task))
            session.commit()

    def save_run(self, envelope: CalculationEnvelope, request_id: str) -> None:
        result = envelope.result
        validation = envelope.validation
        with Session(self.engine) as session:
            session.add(
                CalculationRunRow(
                    id=result.run_id,
                    request_id=request_id,
                    task_id=result.task_id,
                    status=validation.overall_status,
                    input_snapshot=result.input_snapshot,
                    result_snapshot=result.model_dump(mode="json"),
                    validation_snapshot=validation.model_dump(mode="json"),
                    software_version=result.backend_version,
                )
            )
            for ordinal, point in enumerate(result.points):
                session.add(
                    CalculationPointRow(
                        run_id=result.run_id,
                        ordinal=ordinal,
                        temperature_K=point.temperature_K,
                        pressure_kPa=point.pressure_kPa,
                        liquid_composition=point.liquid_composition,
                        vapor_composition=point.vapor_composition,
                    )
                )
            session.add(
                ValidationReportRow(
                    run_id=result.run_id,
                    overall_status=validation.overall_status,
                    report=validation.model_dump(mode="json"),
                )
            )
            for source in envelope.parameter_sources:
                session.add(
                    EvidenceRecordRow(
                        run_id=result.run_id,
                        category="Database",
                        source_identifier=source.get("source_identifier"),
                        payload=source,
                    )
                )
            for recommendation in envelope.model_recommendations:
                session.add(
                    EvidenceRecordRow(
                        run_id=result.run_id,
                        category="Inference",
                        source_identifier=None,
                        payload=recommendation.model_dump(mode="json"),
                    )
                )
            session.commit()

    def get_run(self, run_id: str) -> RunRecord | None:
        with Session(self.engine) as session:
            row = session.get(CalculationRunRow, run_id)
            if row is None:
                return None
            return RunRecord(
                run_id=row.id,
                request_id=row.request_id,
                task_id=row.task_id,
                status=row.status,
                input_snapshot=row.input_snapshot,
                result=row.result_snapshot,
                validation=row.validation_snapshot,
                created_at=row.created_at,
            )

    def add_parameter_set(self, parameter_set: ParameterSet) -> None:
        if parameter_set.source_type == "test_fixture":
            raise ValueError("test_fixture parameter sets cannot enter the production database")
        row = ParameterSetRow(
            id=parameter_set.parameter_set_id,
            model_name=parameter_set.model_name,
            component_key="|".join(parameter_set.component_order),
            payload=parameter_set.model_dump(mode="json"),
            source_type=parameter_set.source_type,
        )
        with Session(self.engine) as session:
            session.add(row)
            session.commit()

    def search_parameter_sets(self, model_name: str | None, components: list[str]) -> list[ParameterSet]:
        with Session(self.engine) as session:
            query = select(ParameterSetRow)
            if model_name:
                query = query.where(ParameterSetRow.model_name == model_name)
            rows = session.scalars(query).all()
        requested = set(components)
        results: list[ParameterSet] = []
        for row in rows:
            parameter_set = ParameterSet.model_validate(row.payload)
            if not requested or set(parameter_set.component_order) == requested:
                results.append(parameter_set)
        return results

    def record_export(self, run_id: str, format_name: str) -> None:
        with Session(self.engine) as session:
            session.add(ExportRecordRow(run_id=run_id, format=format_name))
            session.commit()
