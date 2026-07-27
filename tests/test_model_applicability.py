from __future__ import annotations

from schemas.domain import ComponentIdentity, TaskManifest, ThermodynamicConditions
from schemas.model_applicability import ModelApplicabilityRequest
from thermo_engine.model_applicability import filter_applicable_models

BENZENE = ComponentIdentity(component_id="benzene", name="Benzene", cas_number="71-43-2")
TOLUENE = ComponentIdentity(component_id="toluene", name="Toluene", cas_number="108-88-3")


def _task(
    calculation_type: str = "isobaric_vle",
    *,
    equilibrium_type: str = "VLE",
    model_name: str | None = None,
) -> TaskManifest:
    conditions = ThermodynamicConditions(pressure_kPa=101.325)
    return TaskManifest(
        equilibrium_type=equilibrium_type,
        calculation_type=calculation_type,
        components=[BENZENE, TOLUENE],
        conditions=conditions,
        model_name=model_name,
    )


def _result_by_name(request: ModelApplicabilityRequest) -> dict[str, tuple[str, list[str]]]:
    report = filter_applicable_models(request)
    return {result.model_name: (result.decision, result.reasons) for result in report.results}


def test_filter_applicable_models_returns_all_catalog_entries() -> None:
    results = _result_by_name(ModelApplicabilityRequest(task=_task()))

    assert len(results) == 7
    assert set(results) == {
        "Ideal/Raoult",
        "Peng-Robinson",
        "Phasepy/Peng-Robinson",
        "Clapeyron/Peng-Robinson",
        "Wilson",
        "NRTL",
        "UNIQUAC",
    }


def test_keep_result_has_positive_reason_when_no_rules_exclude() -> None:
    results = _result_by_name(
        ModelApplicabilityRequest(
            task=_task(),
            available_parameter_models={"Peng-Robinson"},
        )
    )

    decision, reasons = results["Peng-Robinson"]
    assert decision == "keep"
    assert reasons == ["Kept: the model satisfies the current minimal applicability rules."]


def test_contract_only_model_accumulates_all_applicable_exclusion_reasons() -> None:
    results = _result_by_name(ModelApplicabilityRequest(task=_task()))

    decision, reasons = results["NRTL"]
    assert decision == "exclude"
    assert any("contract_only" in reason for reason in reasons)
    assert any("not production_ready" in reason for reason in reasons)
    assert any("requires binary parameters" in reason for reason in reasons)


def test_production_only_false_keeps_optional_backend_when_other_rules_pass() -> None:
    results = _result_by_name(
        ModelApplicabilityRequest(
            task=_task(),
            production_only=False,
            available_parameter_models={"Phasepy/Peng-Robinson"},
        )
    )

    decision, reasons = results["Phasepy/Peng-Robinson"]
    assert decision == "keep"
    assert reasons == ["Kept: the model satisfies the current minimal applicability rules."]


def test_production_only_true_excludes_optional_backend() -> None:
    results = _result_by_name(
        ModelApplicabilityRequest(
            task=_task(),
            production_only=True,
            available_parameter_models={"Phasepy/Peng-Robinson"},
        )
    )

    decision, reasons = results["Phasepy/Peng-Robinson"]
    assert decision == "exclude"
    assert any("production_only was requested" in reason for reason in reasons)


def test_missing_binary_parameters_excludes_required_models() -> None:
    results = _result_by_name(ModelApplicabilityRequest(task=_task()))

    decision, reasons = results["Peng-Robinson"]
    assert decision == "exclude"
    assert any("requires binary parameters" in reason for reason in reasons)


def test_calculation_type_mismatch_excludes_model() -> None:
    results = _result_by_name(
        ModelApplicabilityRequest(
            task=_task("tp_flash"),
            production_only=False,
            available_parameter_models={"Wilson"},
        )
    )

    decision, reasons = results["Wilson"]
    assert decision == "exclude"
    assert any("calculation_type 'tp_flash'" in reason for reason in reasons)


def test_equilibrium_type_mismatch_excludes_model() -> None:
    results = _result_by_name(
        ModelApplicabilityRequest(
            task=_task("lle", equilibrium_type="LLE"),
            production_only=False,
            available_parameter_models={"Ideal/Raoult"},
        )
    )

    decision, reasons = results["Ideal/Raoult"]
    assert decision == "exclude"
    assert any("equilibrium_type 'LLE'" in reason for reason in reasons)
