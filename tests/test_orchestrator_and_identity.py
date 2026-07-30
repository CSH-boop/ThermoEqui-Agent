"""Tests for orchestrator task parsing and component identity heuristics."""

from __future__ import annotations

import pytest

from agent.orchestrator import ConversationOrchestrator, DeterministicProvider
from agent.providers import LLMProviderOutputError
from schemas.domain import ComponentIdentity, TaskManifest, ThermodynamicConditions
from thermo_engine.identity import has_chemical_role_evidence, is_electrolyte_identity, resolve_literal_components


def test_has_chemical_role_evidence_accepts_component_in_equilibrium_phrase() -> None:
    message = "计算苯在101.325 kPa下的T-x-y曲线"
    start = message.index("苯")
    end = start + len("苯")
    assert has_chemical_role_evidence(message, start, end)


def test_resolve_literal_components_finds_cas_and_name() -> None:
    message = "Methane and ethane at 100 kPa"
    resolved = resolve_literal_components(message)
    assert [component.cas_number for _, component in resolved] == ["74-82-8", "74-84-0"]


def test_electrolyte_identity_detects_known_salt() -> None:
    component = ComponentIdentity(component_id="nacl", name="Sodium chloride", cas_number="7647-14-5")
    assert is_electrolyte_identity(component)


def test_electrolyte_identity_rejects_non_electrolyte_gas() -> None:
    component = ComponentIdentity(component_id="nitrogen", name="Nitrogen", cas_number="7727-37-9")
    assert not is_electrolyte_identity(component)


@pytest.mark.asyncio
async def test_formulate_task_extracts_binary_components_from_chinese_system_phrase() -> None:
    provider = DeterministicProvider()

    task = await provider.formulate_task("乙醇-水体系进行VLE计算")

    assert task is not None
    assert [component.component_id for component in task.components] == ["ethanol", "water"]


@pytest.mark.asyncio
async def test_conversation_orchestrator_returns_warning_for_unsupported_electrolyte_task() -> None:
    provider = DeterministicProvider()
    orchestrator = ConversationOrchestrator(provider)

    response = await orchestrator.chat("计算氯化钠在100 kPa下的相平衡")

    assert response.intent.name == "UNSUPPORTED_TASK"
    assert response.calculation is None
    assert any("超出" in statement.text for statement in response.statements)
