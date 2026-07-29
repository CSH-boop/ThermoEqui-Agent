"""Tests for model card loading and deterministic recommendation logic."""

from __future__ import annotations

from schemas.domain import ComponentIdentity, TaskManifest, ThermodynamicConditions
from agent.router import load_model_cards, recommend_models


def test_load_model_cards_contains_expected_models() -> None:
    cards = load_model_cards()
    assert {card.model_name for card in cards} == {
        "Ideal/Raoult",
        "Peng-Robinson",
        "Wilson",
        "NRTL",
        "UNIQUAC",
    }


def test_recommend_models_marks_peng_robinson_executable_when_parameters_available() -> None:
    task = TaskManifest(
        equilibrium_type="VLE",
        calculation_type="isobaric_vle",
        components=[
            ComponentIdentity(component_id="methane", name="Methane", cas_number="74-82-8"),
            ComponentIdentity(component_id="ethane", name="Ethane", cas_number="74-84-0"),
        ],
        conditions=ThermodynamicConditions(pressure_kPa=800.0),
        points=11,
    )
    recommendations = recommend_models(task, available_parameter_models={"Peng-Robinson"})
    pr = next(item for item in recommendations if item.model_name == "Peng-Robinson")
    assert pr.executable
    nrtl = next(item for item in recommendations if item.model_name == "NRTL")
    assert not nrtl.executable


def test_recommend_models_excludes_wilson_for_lle() -> None:
    task = TaskManifest(
        equilibrium_type="LLE",
        calculation_type="lle",
        components=[
            ComponentIdentity(component_id="benzene", name="Benzene", cas_number="71-43-2"),
            ComponentIdentity(component_id="toluene", name="Toluene", cas_number="108-88-3"),
        ],
        conditions=ThermodynamicConditions(temperature_K=298.15),
        points=21,
    )
    recommendations = recommend_models(task)
    wilson = next(item for item in recommendations if item.model_name == "Wilson")
    assert any("hard-excluded for LLE" in exclusion for exclusion in wilson.exclusions)
