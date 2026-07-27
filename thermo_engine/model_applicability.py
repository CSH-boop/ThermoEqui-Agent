"""Apply minimal applicability filtering rules to model catalog entries."""

from __future__ import annotations

from schemas.model_applicability import (
    ModelApplicabilityReport,
    ModelApplicabilityRequest,
    ModelApplicabilityResult,
)
from schemas.model_catalog import ModelCatalogEntry
from thermo_engine.model_catalog import load_model_catalog


def evaluate_model_applicability(
    entry: ModelCatalogEntry, request: ModelApplicabilityRequest
) -> ModelApplicabilityResult:
    reasons: list[str] = []
    task = request.task
    available_parameter_models = {name.casefold() for name in request.available_parameter_models}

    if task.calculation_type not in entry.supported_calculation_types:
        reasons.append(
            f"Excluded: calculation_type {task.calculation_type!r} is not supported by {entry.name}."
        )
    if task.equilibrium_type not in entry.supported_equilibrium_types:
        reasons.append(
            f"Excluded: equilibrium_type {task.equilibrium_type!r} is not supported by {entry.name}."
        )
    if entry.implementation_status == "contract_only":
        reasons.append(f"Excluded: {entry.name} is contract_only and not executable in the current product.")
    if request.production_only and not entry.production_ready:
        reasons.append(
            f"Excluded: production_only was requested and {entry.name} is not production_ready."
        )
    if entry.requires_binary_parameters and entry.name.casefold() not in available_parameter_models:
        reasons.append(
            f"Excluded: {entry.name} requires binary parameters, but no reviewed parameter set is available."
        )

    if reasons:
        return ModelApplicabilityResult(model_name=entry.name, decision="exclude", reasons=reasons)

    return ModelApplicabilityResult(
        model_name=entry.name,
        decision="keep",
        reasons=["Kept: the model satisfies the current minimal applicability rules."],
    )


def filter_applicable_models(request: ModelApplicabilityRequest) -> ModelApplicabilityReport:
    catalog = load_model_catalog()
    return ModelApplicabilityReport(
        results=[evaluate_model_applicability(entry, request) for entry in catalog.values()]
    )
