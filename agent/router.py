"""Hard-rule exclusion and explainable thermodynamic model ranking."""

from __future__ import annotations

from pathlib import Path

import yaml

from schemas.domain import (
    ModelCard,
    ModelRecommendation,
    ScoreBreakdown,
    SystemProfile,
    TaskManifest,
)
from schemas.model_applicability import ModelAllowanceRequest
from thermo_engine.model_applicability import is_model_allowed
from thermo_engine.properties import resolve_component

CARD_DIRECTORY = Path(__file__).resolve().parents[1] / "knowledge" / "model_cards"


def load_model_cards() -> list[ModelCard]:
    return [
        ModelCard.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted(CARD_DIRECTORY.glob("*.yaml"))
    ]


def profile_system(task: TaskManifest) -> SystemProfile:
    names = " ".join(
        value for component in task.components for value in (component.component_id, component.name, *component.aliases)
    )
    electrolyte_markers = ("sodium", "chloride", "nacl", "氯化钠", "电解质", "盐水")
    is_electrolyte = any(marker in names.casefold() for marker in electrolyte_markers)
    resolved = []
    for component in task.components:
        try:
            resolved.append(resolve_component(component))
        except Exception:
            pass
    pressure = task.conditions.pressure_kPa
    regime = "unknown" if pressure is None else "low" if pressure <= 500 else "moderate" if pressure <= 5000 else "high"
    all_hydrocarbons = len(resolved) == len(task.components) and all(c.hydrocarbon for c in resolved)
    is_polar = any(c.polar for c in resolved)
    association = any(c.association_risk for c in resolved)
    supported = not is_electrolyte and task.equilibrium_type in {"VLE", "FLASH", "LLE"}
    return SystemProfile(
        component_count=len(task.components),
        is_electrolyte=is_electrolyte,
        all_hydrocarbons=all_hydrocarbons,
        is_polar=is_polar,
        association_risk=association,
        pressure_regime=regime,
        phase_split_risk="high" if task.equilibrium_type == "LLE" else "low",
        supported=supported,
        evidence=["Profile fields were generated from structured component records and rules."],
    )


def recommend_models(
    task: TaskManifest, available_parameter_models: set[str] | None = None
) -> list[ModelRecommendation]:
    available = {name.casefold() for name in (available_parameter_models or set())}
    profile = profile_system(task)
    recommendations: list[ModelRecommendation] = []
    for card in load_model_cards():
        exclusions: list[str] = []
        reasons: list[str] = []
        phase_supported = task.equilibrium_type in card.supported_tasks
        if not phase_supported:
            exclusions.append(f"{card.model_name} does not support {task.equilibrium_type}.")
        if profile.is_electrolyte:
            exclusions.append("Electrolytes are outside the current product scope.")
        if task.equilibrium_type == "LLE" and card.model_name == "Wilson":
            exclusions.append("Wilson is hard-excluded for LLE.")
        has_parameters = not card.requires_binary_parameters or card.model_name.casefold() in available
        if not has_parameters:
            reasons.append("Required binary parameters are unavailable; execution is blocked.")
        applicability = is_model_allowed(
            ModelAllowanceRequest(
                model_name=card.model_name,
                calculation_type=task.calculation_type,
                equilibrium_type=task.equilibrium_type,
                available_parameters=available_parameter_models or set(),
            )
        )
        if not applicability.allowed:
            exclusions.append(applicability.reason)
        phase_score = 30.0 if phase_supported else 0.0
        if profile.pressure_regime == "high":
            system_score = 25.0 if card.family == "cubic_eos" else 2.0
        elif profile.is_polar:
            system_score = 23.0 if card.model_name in {"NRTL", "UNIQUAC"} else 8.0
        else:
            system_score = 24.0 if card.model_name in {"Ideal/Raoult", "Wilson"} else 14.0
        condition_score = 15.0 if profile.pressure_regime in card.pressure_regime else 3.0
        parameter_score = 15.0 if has_parameters else 0.0
        evidence_score = 10.0 if not card.requires_binary_parameters else 6.0 if has_parameters else 0.0
        extrapolation_penalty = 0.0
        numerical_penalty = 0.0 if card.implementation_status == "available" else 12.0
        breakdown = ScoreBreakdown(
            phase_support_score=phase_score,
            system_match_score=system_score,
            condition_match_score=condition_score,
            parameter_availability_score=parameter_score,
            evidence_quality_score=evidence_score,
            extrapolation_penalty=extrapolation_penalty,
            numerical_risk_penalty=numerical_penalty,
        )
        executable = not exclusions and applicability.allowed
        reasons.extend(
            [
                f"Phase support: {'matched' if phase_supported else 'not matched'}.",
                f"System fit: profile is {profile.pressure_regime}-pressure; model family is {card.family}.",
                f"Implementation: {card.implementation_status}.",
            ]
        )
        recommendations.append(
            ModelRecommendation(
                model_name=card.model_name,
                score=breakdown.total,
                executable=executable,
                reasons=reasons,
                exclusions=exclusions,
                breakdown=breakdown,
            )
        )
    return sorted(recommendations, key=lambda item: item.score, reverse=True)
