"""Persistence tests for immutable runs and fixture exclusion."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine

from database.session import Repository, initialize_database
from schemas.domain import ParameterSet


def test_test_fixture_parameter_cannot_enter_production_repository() -> None:
    engine = create_engine("sqlite:///:memory:")
    initialize_database(engine)
    repository = Repository(engine)
    fixture = ParameterSet.model_validate_json(
        (Path(__file__).parent / "fixtures" / "synthetic_nrtl.json").read_text(encoding="utf-8")
    )
    with pytest.raises(ValueError, match="cannot enter"):
        repository.add_parameter_set(fixture)
