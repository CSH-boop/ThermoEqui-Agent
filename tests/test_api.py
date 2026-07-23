"""HTTP contract tests through the FastAPI application seam."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import apps.api.main as api_module
from agent.orchestrator import ConversationOrchestrator
from agent.providers import DeepSeekProvider
from database.models import EvidenceRecordRow
from database.session import Repository, initialize_database


def client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    initialize_database(engine)
    api_module.repository = Repository(engine)

    @asynccontextmanager
    async def no_op_lifespan(_):  # type: ignore[no-untyped-def]
        yield

    api_module.app.router.lifespan_context = no_op_lifespan
    return TestClient(api_module.app)


def test_health_and_error_responses_have_request_id() -> None:
    with client() as test_client:
        response = test_client.get("/health", headers={"X-Request-ID": "request-test"})
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == "request-test"
        bad = test_client.post(
            "/api/calculations/isobaric-vle",
            json={
                "equilibrium_type": "VLE",
                "calculation_type": "isobaric_vle",
                "components": [
                    {"component_id": "benzene", "name": "Benzene"},
                    {"component_id": "toluene", "name": "Toluene"},
                ],
                "conditions": {},
            },
        )
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "missing_data"


def test_chat_persists_real_run_and_exports_json_and_csv() -> None:
    with client() as test_client:
        response = test_client.post("/api/chat", json={"message": "计算苯-甲苯在101.325 kPa下的T-x-y曲线"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["calculation"]["validation"]["overall_status"] in {"passed", "warning"}
        assert [step["phase"] for step in payload["execution_steps"]] == [
            "plan",
            "execute",
            "validate",
            "respond",
        ]
        assert payload["execution_steps"][1]["tool_name"] == "phase_equilibrium"
        run_id = payload["calculation"]["result"]["run_id"]
        run = test_client.get(f"/api/runs/{run_id}")
        assert run.status_code == 200
        assert run.json()["input_snapshot"]["conditions"]["pressure_kPa"] == 101.325
        exported_json = test_client.get(f"/api/runs/{run_id}/export?format=json")
        exported_csv = test_client.get(f"/api/runs/{run_id}/export?format=csv")
        assert exported_json.status_code == 200
        assert exported_csv.status_code == 200
        assert "temperature_K" in exported_csv.text
        with Session(api_module.repository.engine) as session:
            evidence_count = session.scalar(
                select(func.count()).select_from(EvidenceRecordRow).where(EvidenceRecordRow.run_id == run_id)
            )
        assert evidence_count is not None and evidence_count > 0


def test_openapi_contains_all_required_routes() -> None:
    expected = {
        "/api/chat",
        "/api/tasks/parse",
        "/api/models/recommend",
        "/api/models",
        "/api/parameters",
        "/api/parameters/search",
        "/api/calculations/bubble-point",
        "/api/calculations/dew-point",
        "/api/calculations/isobaric-vle",
        "/api/calculations/isothermal-vle",
        "/api/calculations/tp-flash",
        "/api/calculations/azeotrope",
        "/api/calculations/lle",
        "/api/validation",
        "/api/runs/{run_id}",
        "/api/runs/{run_id}/export",
        "/health",
    }
    assert expected <= set(api_module.app.openapi()["paths"])


def test_peng_robinson_api_returns_thermo_and_chemsep_provenance() -> None:
    task = {
        "equilibrium_type": "FLASH",
        "calculation_type": "tp_flash",
        "components": [
            {"component_id": "methane", "name": "Methane", "cas_number": "74-82-8"},
            {"component_id": "ethane", "name": "Ethane", "cas_number": "74-84-0"},
            {"component_id": "nitrogen", "name": "Nitrogen", "cas_number": "7727-37-9"},
        ],
        "conditions": {
            "temperature_K": 110.0,
            "pressure_kPa": 100.0,
            "feed_composition": [0.965, 0.018, 0.017],
        },
        "model_name": "Peng-Robinson",
    }

    with client() as test_client:
        response = test_client.post("/api/calculations/tp-flash", json=task)

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["backend_version"].startswith("thermo/")
    assert payload["result"]["parameter_set_id"].startswith("chemsep-pr:")
    assert payload["validation"]["material_balance"]["passed"]
    assert any(source["source_title"] == "ChemSep PR" for source in payload["parameter_sources"])
    assert any(source["source_title"] == "CalebBell/thermo" for source in payload["parameter_sources"])
    interaction_source = next(
        source for source in payload["parameter_sources"] if source["source_title"] == "ChemSep PR"
    )
    assert '"74-82-8"' in interaction_source["component_order"]
    assert interaction_source["parameter_set_id"] == payload["result"]["parameter_set_id"]
    recommendation = next(item for item in payload["model_recommendations"] if item["model_name"] == "Peng-Robinson")
    assert recommendation["executable"]


def test_deepseek_chat_normalizes_tp_flash_alias_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        "EQUILIBRIUM_CALCULATION",
        json.dumps(
            {
                "equilibrium_type": "FLASH",
                "calculation_type": "TP-FLASH",
                "components": [
                    {"component_id": "methane", "name": "Methane", "cas_number": "74-82-8"},
                    {"component_id": "ethane", "name": "Ethane", "cas_number": "74-84-0"},
                    {"component_id": "nitrogen", "name": "Nitrogen", "cas_number": "7727-37-9"},
                ],
                "conditions": {
                    "temperature_K": 110.0,
                    "pressure_kPa": 100.0,
                    "feed_composition": [0.965, 0.018, 0.017],
                },
                "model_name": "Peng-Robinson",
            }
        ),
        json.dumps({"tool_name": "phase_equilibrium"}),
        "The deterministic result and validation payload were received.",
    ]
    request_count = 0

    async def respond(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        content = responses[request_count]
        request_count += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    provider = DeepSeekProvider(
        api_key="test-key",
        transport=httpx.MockTransport(respond),
    )
    monkeypatch.setattr(api_module, "orchestrator", ConversationOrchestrator(provider))

    with client() as test_client:
        response = test_client.post(
            "/api/chat",
            json={
                "message": (
                    "Calculate methane, ethane and nitrogen TP Flash at 110 K and 100 kPa "
                    "with composition 0.965, 0.018, 0.017."
                )
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["calculation_type"] == "tp_flash"
    assert payload["calculation"]["result"]["backend_version"].startswith("thermo/")
    assert payload["calculation"]["validation"]["material_balance"]["passed"]


def test_request_validation_and_not_found_use_unified_error_shape() -> None:
    with client() as test_client:
        invalid = test_client.post(
            "/api/models/recommend",
            json={
                "equilibrium_type": "VLE",
                "calculation_type": "isobaric_vle",
                "components": [{"component_id": "benzene", "name": "Benzene"}],
                "conditions": {"pressure_kPa": -1},
            },
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "request_validation_error"
        missing = test_client.get("/api/runs/not-found")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "http_404"


def test_deepseek_failure_returns_sanitized_gateway_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def reject(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "server-secret-detail"}})

    provider = DeepSeekProvider(
        api_key="test-key",
        transport=httpx.MockTransport(reject),
    )
    monkeypatch.setattr(api_module, "orchestrator", ConversationOrchestrator(provider))

    with client() as test_client:
        response = test_client.post("/api/chat", json={"message": "解释 NRTL"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "external_llm_provider_error"
    assert "test-key" not in response.text
    assert "server-secret-detail" not in response.text


def test_invalid_deepseek_intent_falls_back_to_deterministic_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        "NONE",
        "NRTL 是液相活度系数模型；Peng-Robinson 是立方状态方程。",
    ]
    request_count = 0

    async def respond(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        content = responses[request_count]
        request_count += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    provider = DeepSeekProvider(
        api_key="test-key",
        transport=httpx.MockTransport(respond),
    )
    monkeypatch.setattr(api_module, "orchestrator", ConversationOrchestrator(provider))

    with client() as test_client:
        response = test_client.post("/api/chat", json={"message": "NRTL和Peng-Robinson有什么区别？"})

    assert response.status_code == 200
    assert response.json()["intent"] == "MODEL_SELECTION_QA"
    assert request_count == 2


def test_unparseable_deepseek_task_is_reported_as_gateway_error(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        "EQUILIBRIUM_CALCULATION",
        "not-a-task-manifest",
        "still-not-a-task-manifest",
    ]
    request_count = 0

    async def respond(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        content = responses[request_count]
        request_count += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    provider = DeepSeekProvider(
        api_key="test-key",
        transport=httpx.MockTransport(respond),
    )
    monkeypatch.setattr(api_module, "orchestrator", ConversationOrchestrator(provider))

    with client() as test_client:
        response = test_client.post("/api/chat", json={"message": "计算苯-甲苯的T-x-y曲线"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "external_llm_output_error"
    assert "not-a-task-manifest" not in response.text


def test_malformed_deepseek_envelope_is_reported_as_sanitized_gateway_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "upstream-private-content"})

    provider = DeepSeekProvider(
        api_key="test-key",
        transport=httpx.MockTransport(respond),
    )
    monkeypatch.setattr(api_module, "orchestrator", ConversationOrchestrator(provider))

    with client() as test_client:
        response = test_client.post("/api/chat", json={"message": "解释 NRTL"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "external_llm_output_error"
    assert "upstream-private-content" not in response.text
