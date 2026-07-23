"""Shared deterministic calculate-validate-evidence workflow."""

from agent.router import recommend_models
from schemas.domain import CalculationEnvelope, TaskManifest
from thermo_engine.service import (
    calculate_equilibrium,
    resolve_backend,
    route_task_model,
    validate_equilibrium_result,
)


def execute_task(task: TaskManifest) -> CalculationEnvelope:
    task = route_task_model(task)
    backend = resolve_backend(task)
    result = calculate_equilibrium(task, backend=backend)
    validation = validate_equilibrium_result(result)
    return CalculationEnvelope(
        result=result,
        validation=validation,
        parameter_sources=backend.parameter_sources(task),
        model_recommendations=recommend_models(
            task,
            available_parameter_models={task.model_name} if task.model_name is not None else set(),
        ),
    )
