"""Behavioral evaluations at the public conversation orchestrator seam."""

from __future__ import annotations

import pytest

from agent.orchestrator import ConversationOrchestrator
from agent.router import recommend_models
from schemas.domain import ComponentIdentity, TaskManifest, ThermodynamicConditions


@pytest.mark.asyncio
async def test_knowledge_question_never_invokes_calculation() -> None:
    response = await ConversationOrchestrator().chat("NRTL和Peng-Robinson有什么区别？")
    assert response.intent == "MODEL_SELECTION_QA"
    assert response.task is None
    assert response.calculation is None
    assert response.statements[0].category == "Knowledge"


@pytest.mark.asyncio
async def test_calculation_question_generates_manifest_and_real_curve() -> None:
    response = await ConversationOrchestrator().chat("计算苯-甲苯在101.325 kPa下的T-x-y曲线")
    assert response.task is not None
    assert response.task.calculation_type == "isobaric_vle"
    assert response.calculation is not None
    assert len(response.calculation.result.points) == 21
    assert response.calculation.validation.overall_status in {"passed", "warning"}


@pytest.mark.asyncio
async def test_missing_pressure_is_explicit_and_has_no_fake_result() -> None:
    response = await ConversationOrchestrator().chat("计算苯-甲苯T-x-y曲线")
    assert response.task is not None
    assert response.calculation is None
    assert "pressure_kPa" in response.answer


@pytest.mark.asyncio
async def test_atmospheric_pressure_is_normalized_with_assumption() -> None:
    response = await ConversationOrchestrator().chat("计算苯-甲苯常压VLE")
    assert response.task is not None
    assert response.task.conditions.pressure_kPa == pytest.approx(101.325)
    assert any("101.325" in assumption for assumption in response.task.assumptions)


@pytest.mark.asyncio
async def test_followup_pressure_change_inherits_system_and_creates_new_run() -> None:
    orchestrator = ConversationOrchestrator()
    first = await orchestrator.chat("计算苯-甲苯常压VLE")
    second = await orchestrator.chat("压力改为80 kPa，再算一次", first.conversation_id)
    assert first.task is not None and second.task is not None
    assert [c.component_id for c in second.task.components] == ["benzene", "toluene"]
    assert second.task.conditions.pressure_kPa == pytest.approx(80.0)
    assert second.task.task_id != first.task.task_id
    assert second.calculation is not None
    assert second.calculation.result.run_id != first.calculation.result.run_id  # type: ignore[union-attr]


def test_lle_hard_excludes_wilson() -> None:
    task = TaskManifest(
        equilibrium_type="LLE",
        calculation_type="lle",
        components=[
            ComponentIdentity(component_id="benzene", name="Benzene"),
            ComponentIdentity(component_id="toluene", name="Toluene"),
        ],
        conditions=ThermodynamicConditions(temperature_K=298.15),
    )
    wilson = next(item for item in recommend_models(task, {"Wilson"}) if item.model_name == "Wilson")
    assert not wilson.executable
    assert any("hard-excluded" in reason for reason in wilson.exclusions)


@pytest.mark.asyncio
async def test_electrolyte_task_is_refused_without_solver() -> None:
    response = await ConversationOrchestrator().chat("计算氯化钠水溶液的电解质相平衡")
    assert response.intent == "UNSUPPORTED_TASK"
    assert response.calculation is None
    assert response.statements[0].category == "Warning"


@pytest.mark.asyncio
async def test_parameter_request_does_not_invent_values() -> None:
    response = await ConversationOrchestrator().chat("给我一个本地没有的NRTL参数")
    assert response.intent == "PARAMETER_QUERY"
    assert response.calculation is None
    assert all(not any(char.isdigit() for char in item.text) for item in response.statements)


@pytest.mark.asyncio
async def test_sensitivity_intent_is_recognized_without_unapproved_scan() -> None:
    response = await ConversationOrchestrator().chat("做一下压力敏感性分析")
    assert response.intent == "SENSITIVITY_ANALYSIS"
    assert response.calculation is None
    assert response.statements[0].category == "Warning"


@pytest.mark.asyncio
async def test_lle_request_reaches_lle_contract_without_fake_result() -> None:
    response = await ConversationOrchestrator().chat("计算苯和甲苯在 298.15 K 下的液液平衡 LLE")
    assert response.intent == "EQUILIBRIUM_CALCULATION"
    assert response.task is not None
    assert response.task.equilibrium_type == "LLE"
    assert response.task.calculation_type == "lle"
    assert response.calculation is None
    assert response.statements[0].category == "Warning"
    assert "cannot represent liquid-liquid" in response.answer


@pytest.mark.asyncio
async def test_polymer_request_is_refused_at_scope_boundary() -> None:
    response = await ConversationOrchestrator().chat("计算聚合物溶液的汽液平衡")
    assert response.intent == "UNSUPPORTED_TASK"
    assert response.calculation is None
