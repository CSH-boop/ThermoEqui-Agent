"""Shared deterministic calculate-validate-evidence workflow."""

from agent.router import recommend_models
from schemas.domain import CalculationEnvelope, TaskManifest
from thermo_engine.properties import component_sources, resolve_component
from thermo_engine.service import calculate_equilibrium, validate_equilibrium_result


def execute_task(task: TaskManifest) -> CalculationEnvelope:
    result = calculate_equilibrium(task)
    validation = validate_equilibrium_result(result)
    components = [resolve_component(component) for component in task.components]
    return CalculationEnvelope(
        result=result,
        validation=validation,
        parameter_sources=component_sources(components),
        model_recommendations=recommend_models(task),
    )
