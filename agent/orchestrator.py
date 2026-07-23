"""Single orchestrator with deterministic parsing and tool invocation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import uuid4

from agent.executor import execute_task
from agent.providers import LLMProvider
from schemas.domain import (
    ChatResponse,
    ComponentIdentity,
    EvidenceStatement,
    Intent,
    TaskManifest,
    ThermodynamicConditions,
)
from thermo_engine.errors import ThermoEquiError
from thermo_engine.units import pressure_to_kpa, temperature_to_kelvin

COMPONENT_PATTERNS = (
    ("benzene", "Benzene", "71-43-2", ("苯", "benzene")),
    ("toluene", "Toluene", "108-88-3", ("甲苯", "toluene")),
)


@dataclass
class ConversationState:
    task: TaskManifest | None = None
    run_ids: list[str] = field(default_factory=list)


class DeterministicProvider:
    """No-key provider for supported demonstrations and safe refusals."""

    async def classify_intent(self, message: str) -> Intent:
        lower = message.casefold()
        excluded_markers = (
            "氯化钠",
            "电解质",
            "nacl",
            "sle",
            "固液",
            "v lle",
            "vlle",
            "聚合物",
            "polymer",
            "水合物",
            "hydrate",
            "假组分",
            "pseudocomponent",
            "多晶",
            "polymorph",
            "复杂临界",
            "精馏塔设计",
            "full column design",
            "反应相平衡",
            "reactive equilibrium",
        )
        if any(word in lower for word in excluded_markers):
            return Intent.UNSUPPORTED_TASK
        if any(word in lower for word in ("改为", "改成", "再算", "change", "rerun")):
            return Intent.TASK_CORRECTION
        if any(word in lower for word in ("解释结果", "结果含义", "interpret result")):
            return Intent.RESULT_INTERPRETATION
        if any(word in lower for word in ("敏感性", "sensitivity")):
            return Intent.SENSITIVITY_ANALYSIS
        if any(word in lower for word in ("工艺建议", "流程建议", "process recommendation")):
            return Intent.PROCESS_RECOMMENDATION
        if any(word in lower for word in ("参数", "parameter")):
            return Intent.PARAMETER_QUERY
        if any(word in lower for word in ("数据", "database", "data query")):
            return Intent.DATA_QUERY
        if any(word in lower for word in ("计算", "曲线", "flash", "泡点", "露点", "共沸", "vle", "lle", "液液")):
            return Intent.EQUILIBRIUM_CALCULATION
        if any(word in lower for word in ("区别", "选择", "模型", "difference", "select")):
            return Intent.MODEL_SELECTION_QA
        return Intent.CONCEPT_QA

    async def formulate_task(self, message: str, previous: TaskManifest | None = None) -> TaskManifest | None:
        lower = message.casefold()
        component_list: list[ComponentIdentity] = []
        for component_id, name, cas, aliases in COMPONENT_PATTERNS:
            if any(alias in lower for alias in aliases):
                component_list.append(ComponentIdentity(component_id=component_id, name=name, cas_number=cas))
        pressure, pressure_assumption = self._pressure(message)
        temperature = self._temperature(message)
        if previous and any(word in lower for word in ("改为", "改成", "再算", "change", "rerun")):
            conditions = previous.conditions.model_copy(
                update={
                    **({"pressure_kPa": pressure} if pressure is not None else {}),
                    **({"temperature_K": temperature} if temperature is not None else {}),
                }
            )
            assumptions = [*previous.assumptions]
            if pressure_assumption and pressure_assumption not in assumptions:
                assumptions.append(pressure_assumption)
            return previous.model_copy(
                update={
                    "task_id": str(uuid4()),
                    "conditions": conditions,
                    "assumptions": assumptions,
                    "original_question": message,
                }
            )
        if not component_list:
            return None
        calculation_type = self._calculation_type(lower)
        equilibrium_type = "FLASH" if calculation_type == "tp_flash" else "LLE" if calculation_type == "lle" else "VLE"
        assumptions = [pressure_assumption] if pressure_assumption else []
        conditions = ThermodynamicConditions(temperature_K=temperature, pressure_kPa=pressure)
        return TaskManifest(
            equilibrium_type=equilibrium_type,
            calculation_type=calculation_type,
            components=component_list,
            conditions=conditions,
            requested_outputs=["chart", "table", "validation", "json", "csv"],
            assumptions=assumptions,
            model_name=(
                "Ideal/Raoult"
                if calculation_type != "lle" and {c.component_id for c in component_list} == {"benzene", "toluene"}
                else None
            ),
            original_question=message,
        )

    async def answer_with_evidence(self, message: str) -> list[EvidenceStatement]:
        if "nrtl" in message.casefold() and ("peng" in message.casefold() or "pr" in message.casefold()):
            text = (
                "NRTL 是液相活度系数模型，适合低到中压下的非理想液相 VLE/LLE，通常需要有来源的二元交互参数；"
                "Peng–Robinson 是立方状态方程，直接描述相逸度，常用于中高压烃类 VLE/Flash。两者不能仅凭名称互换。"
            )
        else:
            text = "当前离线知识库可解释模型与验证原则；数值问题必须交给确定性热力学工具。"
        return [EvidenceStatement(category="Knowledge", text=text)]

    async def interpret_result(self, result: dict[str, object]) -> list[EvidenceStatement]:
        status = result.get("validation_status", "unknown")
        return [
            EvidenceStatement(
                category="Calculation",
                text=f"数值来自确定性热力学后端；物理验证状态为 {status}。",
            )
        ]

    @staticmethod
    def _pressure(message: str) -> tuple[float | None, str | None]:
        if "常压" in message or "atmospheric" in message.casefold():
            return 101.325, "“常压”规范化为 101.325 kPa。"
        match = re.search(r"(\d+(?:\.\d+)?)\s*(kpa|mpa|bar|atm)", message, re.IGNORECASE)
        if not match:
            return None, None
        unit = match.group(2).casefold()
        if unit == "kpa":
            return pressure_to_kpa(float(match.group(1)), "kPa"), None
        if unit == "mpa":
            return pressure_to_kpa(float(match.group(1)), "MPa"), None
        if unit == "bar":
            return pressure_to_kpa(float(match.group(1)), "bar"), None
        return pressure_to_kpa(float(match.group(1)), "atm"), None

    @staticmethod
    def _temperature(message: str) -> float | None:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(k|℃|°c|c)\b", message, re.IGNORECASE)
        if not match:
            return None
        if match.group(2).casefold() == "k":
            return temperature_to_kelvin(float(match.group(1)), "K")
        return temperature_to_kelvin(float(match.group(1)), "C")

    @staticmethod
    def _calculation_type(lower: str) -> str:
        if "lle" in lower or "液液" in lower or "liquid-liquid" in lower:
            return "lle"
        if "p-x-y" in lower or "pxy" in lower or "等温" in lower:
            return "isothermal_vle"
        if "flash" in lower:
            return "tp_flash"
        if "泡点" in lower or "bubble" in lower:
            return "bubble_point"
        if "露点" in lower or "dew" in lower:
            return "dew_point"
        if "共沸" in lower or "azeotrope" in lower:
            return "azeotrope"
        return "isobaric_vle"


class ConversationOrchestrator:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or DeterministicProvider()
        self.states: dict[str, ConversationState] = {}

    async def parse(self, message: str, conversation_id: str | None = None) -> tuple[Intent, TaskManifest | None]:
        intent = await self.provider.classify_intent(message)
        state = self.states.get(conversation_id or "")
        task = await self.provider.formulate_task(message, state.task if state else None)
        return intent, task

    async def chat(self, message: str, conversation_id: str | None = None) -> ChatResponse:
        conversation_id = conversation_id or str(uuid4())
        state = self.states.setdefault(conversation_id, ConversationState())
        intent = await self.provider.classify_intent(message)
        if intent == Intent.UNSUPPORTED_TASK:
            return ChatResponse(
                conversation_id=conversation_id,
                intent=intent,
                answer=(
                    "当前版本不支持电解质、聚合物、水合物、假组分、多晶型、SLE、VLLE、"
                    "反应相平衡或完整精馏塔设计；未执行不适用的普通分子模型。"
                ),
                statements=[EvidenceStatement(category="Warning", text="任务超出 0.1 支持边界。")],
            )
        if intent == Intent.SENSITIVITY_ANALYSIS:
            return ChatResponse(
                conversation_id=conversation_id,
                intent=intent,
                answer="已识别敏感性分析意图；该自动工作流列入 Phase 4，当前未执行数值扫描。",
                statements=[EvidenceStatement(category="Warning", text="请逐个修改条件并保留独立运行进行比较。")],
            )
        if intent in {
            Intent.CONCEPT_QA,
            Intent.MODEL_SELECTION_QA,
            Intent.PARAMETER_QUERY,
            Intent.DATA_QUERY,
            Intent.PROCESS_RECOMMENDATION,
            Intent.RESULT_INTERPRETATION,
        }:
            statements = await self.provider.answer_with_evidence(message)
            return ChatResponse(
                conversation_id=conversation_id,
                intent=intent,
                answer="\n".join(item.text for item in statements),
                statements=statements,
            )
        task = await self.provider.formulate_task(message, state.task)
        if task is None:
            return ChatResponse(
                conversation_id=conversation_id,
                intent=intent,
                answer="缺少可识别的组分，尚未执行计算。",
                statements=[EvidenceStatement(category="Warning", text="需要明确组分身份。")],
            )
        state.task = task
        required_missing = self._missing_conditions(task)
        if required_missing:
            return ChatResponse(
                conversation_id=conversation_id,
                intent=intent,
                answer=f"已生成结构化任务，但缺少 {', '.join(required_missing)}，尚未执行计算。",
                statements=[EvidenceStatement(category="Warning", text="缺失必要计算条件。")],
                task=task,
            )
        try:
            envelope = execute_task(task)
            result = envelope.result
            validation = envelope.validation
            state.run_ids.append(envelope.result.run_id)
            statements = await self.provider.interpret_result(
                {
                    "result": result.model_dump(mode="json"),
                    "validation": validation.model_dump(mode="json"),
                }
            )
            return ChatResponse(
                conversation_id=conversation_id,
                intent=intent,
                answer="计算完成。" if validation.overall_status != "failed" else "计算未通过物理验证。",
                statements=statements,
                task=task,
                calculation=envelope,
            )
        except ThermoEquiError as error:
            return ChatResponse(
                conversation_id=conversation_id,
                intent=intent,
                answer=error.detail.message,
                statements=[EvidenceStatement(category="Warning", text=error.detail.recovery_action)],
                task=task,
            )

    @staticmethod
    def _missing_conditions(task: TaskManifest) -> list[str]:
        missing: list[str] = []
        if (
            task.calculation_type in {"isobaric_vle", "bubble_point", "dew_point", "azeotrope"}
            and task.conditions.pressure_kPa is None
        ):
            missing.append("pressure_kPa")
        if task.calculation_type in {"isothermal_vle", "tp_flash"} and task.conditions.temperature_K is None:
            missing.append("temperature_K")
        if task.calculation_type == "tp_flash" and task.conditions.feed_composition is None:
            missing.append("feed_composition")
        if task.calculation_type == "bubble_point" and task.conditions.liquid_composition is None:
            missing.append("liquid_composition")
        if task.calculation_type == "dew_point" and task.conditions.vapor_composition is None:
            missing.append("vapor_composition")
        if task.calculation_type == "lle" and task.conditions.temperature_K is None:
            missing.append("temperature_K")
        return missing
