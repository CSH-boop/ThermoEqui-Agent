"""Shared deterministic calculate-validate-evidence workflow."""

from dataclasses import dataclass

from agent.router import recommend_models
from schemas.domain import CalculationEnvelope, CalculationResult, TaskManifest
from thermo_engine.backend import ThermodynamicBackend
from thermo_engine.service import (
    calculate_equilibrium,
    resolve_backend,
    route_task_model,
    validate_equilibrium_result,
)


@dataclass(frozen=True)
class TaskExecution:
    """Raw deterministic tool output awaiting the independent validation node."""

    task: TaskManifest
    backend: ThermodynamicBackend
    result: CalculationResult


def calculate_task(task: TaskManifest) -> TaskExecution:
    task = route_task_model(task)
    backend = resolve_backend(task)
    result = calculate_equilibrium(task, backend=backend)
    return TaskExecution(task=task, backend=backend, result=result)


def validate_task_execution(execution: TaskExecution) -> CalculationEnvelope:
    validation = validate_equilibrium_result(execution.result)
    return CalculationEnvelope(
        result=execution.result,
        validation=validation,
        parameter_sources=execution.backend.parameter_sources(execution.task),
        model_recommendations=recommend_models(
            execution.task,
            available_parameter_models={execution.task.model_name} if execution.task.model_name is not None else set(),
        ),
    )


def execute_task(task: TaskManifest) -> CalculationEnvelope:
    """Synchronous public seam composing calculation and independent validation."""
    return validate_task_execution(calculate_task(task))
