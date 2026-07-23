"""CalebBell/thermo adapters kept behind the stable backend protocol."""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import version
from math import isfinite, log
from typing import Any, cast

import numpy as np
from thermo import PRMIX, CEOSGas, CEOSLiquid, ChemicalConstantsPackage, FlashVL
from thermo.interaction_parameters import IPDB

from schemas.domain import (
    CalculationResult,
    EquilibriumPoint,
    FailureType,
    PhaseResult,
    TaskManifest,
)
from thermo_engine.errors import ThermoEquiError


class ThermoPengRobinsonBackend:
    """Peng-Robinson VLE and flash calculations executed by ``thermo``."""

    version = f"thermo/{version('thermo')}"
    parameter_table = "ChemSep PR"
    _allowlisted_light_gas_cas = frozenset(
        {
            "124-38-9",  # carbon dioxide
            "630-08-0",  # carbon monoxide
            "1333-74-0",  # hydrogen
            "7727-37-9",  # nitrogen
            "7782-44-7",  # oxygen
            "7440-37-1",  # argon
        }
    )

    def __init__(self) -> None:
        self._parameter_set_id: str | None = None
        self._parameter_sources: list[dict[str, str]] = []

    def parameter_sources(self, request: TaskManifest) -> list[dict[str, str]]:
        if self._parameter_sources:
            return self._parameter_sources
        component_names = " / ".join(component.name for component in request.components)
        return [
            {
                "component": component.name,
                "property": "Pure-component constants and property correlations",
                "source_title": "CalebBell/thermo",
                "source_identifier": "https://github.com/CalebBell/thermo",
                "temperature_range_K": "model-dependent",
            }
            for component in request.components
        ] + [
            {
                "component": component_names,
                "property": "Peng-Robinson binary interaction parameter kij",
                "source_title": "ChemSep PR",
                "source_identifier": (
                    "https://github.com/CalebBell/thermo/tree/master/thermo/Interaction%20Parameters/ChemSep"
                ),
                "temperature_range_K": "temperature-independent",
            }
        ]

    @classmethod
    def _inapplicable_components(cls, constants: Any) -> list[str]:
        inapplicable: list[str] = []
        for name, cas_number, atoms in zip(
            constants.names,
            constants.CASs,
            constants.atomss,
            strict=True,
        ):
            elements = set(atoms)
            is_hydrocarbon = "C" in elements and elements <= {"C", "H"}
            if not is_hydrocarbon and cas_number not in cls._allowlisted_light_gas_cas:
                inapplicable.append(str(name).title())
        return inapplicable

    @classmethod
    def supports_system(cls, request: TaskManifest) -> bool:
        identifiers = [component.cas_number or component.component_id for component in request.components]
        try:
            constants, _ = ChemicalConstantsPackage.from_IDs(identifiers)
        except (ValueError, LookupError, TypeError):
            return False
        return not cls._inapplicable_components(constants)

    @staticmethod
    def _require_pressure(request: TaskManifest) -> float:
        pressure = request.conditions.pressure_kPa
        if pressure is None:
            raise ThermoEquiError(
                FailureType.MISSING_DATA,
                "Pressure is required for this calculation.",
                "Provide a positive pressure in kPa.",
            )
        return pressure

    @staticmethod
    def _require_temperature(request: TaskManifest) -> float:
        temperature = request.conditions.temperature_K
        if temperature is None:
            raise ThermoEquiError(
                FailureType.MISSING_DATA,
                "Temperature is required for this calculation.",
                "Provide a positive temperature in K.",
            )
        return temperature

    @staticmethod
    def _require_composition(request: TaskManifest, field: str) -> list[float]:
        values = getattr(request.conditions, field)
        if values is None:
            raise ThermoEquiError(
                FailureType.MISSING_DATA,
                f"{field} is required for this calculation.",
                f"Provide {len(request.components)} normalized mole fractions.",
            )
        if len(values) != len(request.components):
            raise ThermoEquiError(
                FailureType.SEMANTIC_FAILURE,
                f"{field} length does not match the component count.",
                "Provide one mole fraction per component in component order.",
            )
        return cast(list[float], values)

    def _flasher(self, request: TaskManifest) -> Any:
        identifiers = [component.cas_number or component.component_id for component in request.components]
        try:
            constants, properties = ChemicalConstantsPackage.from_IDs(identifiers)
        except (ValueError, LookupError, TypeError):
            raise ThermoEquiError(
                FailureType.MISSING_DATA,
                "The thermo property database could not resolve every component.",
                "Provide canonical names or CAS numbers supported by the reviewed property source.",
                {"components": identifiers},
            ) from None

        inapplicable_components = self._inapplicable_components(constants)
        if inapplicable_components:
            raise ThermoEquiError(
                FailureType.PARAMETER_OUT_OF_DOMAIN,
                "The current Peng-Robinson adapter is limited to hydrocarbons and reviewed light gases.",
                "Choose a validated association/activity-coefficient model for this system.",
                {"inapplicable_components": inapplicable_components},
            )
        missing_pairs = [
            [constants.CASs[i], constants.CASs[j]]
            for i in range(len(constants.CASs))
            for j in range(i + 1, len(constants.CASs))
            if not IPDB.has_ip_specific(self.parameter_table, [constants.CASs[i], constants.CASs[j]], "kij")
        ]
        if missing_pairs:
            raise ThermoEquiError(
                FailureType.MISSING_PARAMETERS,
                "Peng-Robinson binary interaction parameters are missing for this component set.",
                "Import reviewed kij values or select another applicable model.",
                {"model": "Peng-Robinson", "parameter_table": self.parameter_table, "missing_pairs": missing_pairs},
            )
        kijs = IPDB.get_ip_asymmetric_matrix(self.parameter_table, constants.CASs, "kij")
        parameter_snapshot = {
            "component_order": constants.CASs,
            "matrix": kijs,
            "parameter_form": "Peng-Robinson kij",
            "source_table": self.parameter_table,
            "thermo_version": self.version,
            "units": "dimensionless",
        }
        snapshot_json = json.dumps(parameter_snapshot, sort_keys=True, separators=(",", ":"))
        self._parameter_set_id = f"chemsep-pr:{hashlib.sha256(snapshot_json.encode()).hexdigest()}"
        component_names = " / ".join(component.name for component in request.components)
        self._parameter_sources = [
            {
                "component": component.name,
                "property": "Pure-component constants and property correlations",
                "source_title": "CalebBell/thermo",
                "source_identifier": "https://github.com/CalebBell/thermo",
                "source_version": self.version,
                "temperature_range_K": "model-dependent",
            }
            for component in request.components
        ] + [
            {
                "component": component_names,
                "component_order": json.dumps(constants.CASs),
                "property": "Peng-Robinson binary interaction parameter kij",
                "parameter_form": "symmetric kij matrix",
                "parameter_values": json.dumps(kijs),
                "parameter_units": "dimensionless",
                "parameter_set_id": self._parameter_set_id,
                "quality_level": "upstream database snapshot; engineering review required",
                "source_title": self.parameter_table,
                "source_identifier": (
                    "https://github.com/CalebBell/thermo/tree/master/thermo/Interaction%20Parameters/ChemSep"
                ),
                "source_version": self.version,
                "temperature_range_K": "temperature-independent",
            }
        ]
        eos_kwargs = {
            "Pcs": constants.Pcs,
            "Tcs": constants.Tcs,
            "omegas": constants.omegas,
            "kijs": kijs,
        }
        gas = CEOSGas(
            PRMIX,
            eos_kwargs=eos_kwargs,
            HeatCapacityGases=properties.HeatCapacityGases,
        )
        liquid = CEOSLiquid(
            PRMIX,
            eos_kwargs=eos_kwargs,
            HeatCapacityGases=properties.HeatCapacityGases,
        )
        flasher = FlashVL(constants, properties, liquid=liquid, gas=gas)
        flasher.DEW_BUBBLE_NEWTON_XTOL = 1e-10
        flasher.DEW_BUBBLE_QUASI_NEWTON_XTOL = 1e-10
        return flasher

    @staticmethod
    def _convergence(solution: Any) -> tuple[float, int]:
        convergence = solution.flash_convergence
        if not isinstance(convergence, dict) or "err" not in convergence or "iterations" not in convergence:
            raise ThermoEquiError(
                FailureType.NUMERICAL_NONCONVERGENCE,
                "The thermo flash solver returned no convergence diagnostics.",
                "Do not use this result; review the solver specification and conditions.",
            )
        residual = abs(float(convergence["err"]))
        iterations = int(convergence["iterations"])
        if not isfinite(residual):
            raise ThermoEquiError(
                FailureType.NUMERICAL_NONCONVERGENCE,
                "The thermo flash solver returned a non-finite residual.",
                "Review conditions, component data, and model applicability.",
            )
        return residual, iterations

    @staticmethod
    def _equilibrium_residual(solution: Any) -> float:
        """Independently check component fugacity equality for a returned phase pair."""
        liquid_phase = getattr(solution, "liquid0", None)
        gas_phase = getattr(solution, "gas", None)
        if liquid_phase is None or gas_phase is None:
            return 0.0
        liquid_fugacities = liquid_phase.fugacities()
        vapor_fugacities = gas_phase.fugacities()
        if len(liquid_fugacities) != len(vapor_fugacities):
            raise ThermoEquiError(
                FailureType.PHYSICAL_VALIDATION_FAILURE,
                "The returned phase fugacity vectors have incompatible sizes.",
                "Do not use this result; review the solver output.",
            )
        residuals: list[float] = []
        for liquid, vapor in zip(liquid_fugacities, vapor_fugacities, strict=True):
            liquid_value = float(liquid)
            vapor_value = float(vapor)
            if abs(liquid_value) <= 1e-30 and abs(vapor_value) <= 1e-30:
                continue
            if liquid_value <= 0.0 or vapor_value <= 0.0 or not isfinite(liquid_value) or not isfinite(vapor_value):
                raise ThermoEquiError(
                    FailureType.PHYSICAL_VALIDATION_FAILURE,
                    "The returned phase fugacities are non-positive or non-finite.",
                    "Do not use this result; review conditions, properties, and model applicability.",
                )
            residuals.append(abs(log(liquid_value / vapor_value)))
        return max(residuals, default=0.0)

    def _flash(self, request: TaskManifest, **specifications: object) -> Any:
        try:
            return self._flasher(request).flash(**specifications)
        except ThermoEquiError:
            raise
        except (ValueError, RuntimeError, ZeroDivisionError, OverflowError):
            raise ThermoEquiError(
                FailureType.NUMERICAL_NONCONVERGENCE,
                "The thermo Peng-Robinson solver did not converge.",
                "Review the phase specification, conditions, and parameter applicability.",
            ) from None

    @staticmethod
    def _point(solution: Any) -> EquilibriumPoint:
        liquid_phase = getattr(solution, "liquid0", None)
        gas_phase = getattr(solution, "gas", None)
        if liquid_phase is None or gas_phase is None:
            raise ThermoEquiError(
                FailureType.PHYSICAL_VALIDATION_FAILURE,
                "A requested phase-boundary calculation did not return both phases.",
                "Review the phase specification and model applicability.",
            )
        ThermoPengRobinsonBackend._convergence(solution)
        return EquilibriumPoint(
            temperature_K=float(solution.T),
            pressure_kPa=float(solution.P) / 1000.0,
            liquid_composition=[float(value) for value in liquid_phase.zs],
            vapor_composition=[float(value) for value in gas_phase.zs],
            equilibrium_residual=ThermoPengRobinsonBackend._equilibrium_residual(solution),
        )

    def _result(
        self,
        request: TaskManifest,
        solution: Any,
        *,
        points: list[EquilibriumPoint] | None = None,
        warnings: list[str] | None = None,
    ) -> CalculationResult:
        solver_residual, iterations = self._convergence(solution)
        equilibrium_residual = self._equilibrium_residual(solution)
        phases: list[PhaseResult] = []
        vapor_fraction = float(solution.VF)
        liquid_phase = getattr(solution, "liquid0", None)
        gas_phase = getattr(solution, "gas", None)
        if liquid_phase is not None:
            phases.append(
                PhaseResult(
                    phase="liquid",
                    fraction=1.0 - vapor_fraction,
                    composition=[float(value) for value in liquid_phase.zs],
                )
            )
        if gas_phase is not None:
            phases.append(
                PhaseResult(
                    phase="vapor",
                    fraction=vapor_fraction,
                    composition=[float(value) for value in gas_phase.zs],
                )
            )
        phase_state = "liquid" if vapor_fraction <= 1e-12 else "vapor" if vapor_fraction >= 1.0 - 1e-12 else "two_phase"
        return CalculationResult(
            task_id=request.task_id,
            calculation_type=request.calculation_type,
            input_snapshot=request.model_dump(mode="json"),
            model_name="Peng-Robinson",
            parameter_set_id=self._parameter_set_id,
            points=points or [],
            phases=phases,
            temperature_K=float(solution.T),
            pressure_kPa=float(solution.P) / 1000.0,
            vapor_fraction=vapor_fraction,
            phase_state=phase_state,
            converged=solver_residual <= 1e-6,
            residual=equilibrium_residual,
            iterations=iterations,
            warnings=[
                "ChemSep PR parameter applicability requires engineering review.",
                *(warnings or []),
            ],
            backend_version=self.version,
            solver_name="thermo.FlashVL / PRMIX",
        )

    def bubble_point(self, request: TaskManifest) -> CalculationResult:
        pressure = self._require_pressure(request)
        liquid = self._require_composition(request, "liquid_composition")
        solution = self._flash(request, P=pressure * 1000.0, VF=0.0, zs=liquid)
        return self._result(request, solution, points=[self._point(solution)])

    def dew_point(self, request: TaskManifest) -> CalculationResult:
        pressure = self._require_pressure(request)
        vapor = self._require_composition(request, "vapor_composition")
        solution = self._flash(request, P=pressure * 1000.0, VF=1.0, zs=vapor)
        return self._result(request, solution, points=[self._point(solution)])

    def isobaric_vle(self, request: TaskManifest) -> CalculationResult:
        if len(request.components) != 2:
            raise ThermoEquiError(
                FailureType.UNSUPPORTED_MODEL,
                "The curve endpoint currently supports binary mixtures only.",
                "Provide exactly two components or use a point/flash calculation.",
            )
        pressure = self._require_pressure(request)
        points: list[EquilibriumPoint] = []
        iterations = 0
        converged = True
        for fraction in np.linspace(0.0, 1.0, request.points):
            solution = self._flash(
                request,
                P=pressure * 1000.0,
                VF=0.0,
                zs=[float(fraction), float(1.0 - fraction)],
            )
            points.append(self._point(solution))
            solver_residual, point_iterations = self._convergence(solution)
            converged = converged and solver_residual <= 1e-6
            iterations += point_iterations
        return CalculationResult(
            task_id=request.task_id,
            calculation_type=request.calculation_type,
            input_snapshot=request.model_dump(mode="json"),
            model_name="Peng-Robinson",
            parameter_set_id=self._parameter_set_id,
            points=points,
            pressure_kPa=pressure,
            phase_state="curve",
            converged=converged,
            residual=max(point.equilibrium_residual for point in points),
            iterations=iterations,
            warnings=["ChemSep PR parameter applicability requires engineering review."],
            backend_version=self.version,
            solver_name="thermo.FlashVL / PRMIX",
        )

    def isothermal_vle(self, request: TaskManifest) -> CalculationResult:
        if len(request.components) != 2:
            raise ThermoEquiError(
                FailureType.UNSUPPORTED_MODEL,
                "The curve endpoint currently supports binary mixtures only.",
                "Provide exactly two components or use a point/flash calculation.",
            )
        temperature = self._require_temperature(request)
        points: list[EquilibriumPoint] = []
        iterations = 0
        converged = True
        for fraction in np.linspace(0.0, 1.0, request.points):
            solution = self._flash(
                request,
                T=temperature,
                VF=0.0,
                zs=[float(fraction), float(1.0 - fraction)],
            )
            points.append(self._point(solution))
            solver_residual, point_iterations = self._convergence(solution)
            converged = converged and solver_residual <= 1e-6
            iterations += point_iterations
        return CalculationResult(
            task_id=request.task_id,
            calculation_type=request.calculation_type,
            input_snapshot=request.model_dump(mode="json"),
            model_name="Peng-Robinson",
            parameter_set_id=self._parameter_set_id,
            points=points,
            temperature_K=temperature,
            phase_state="curve",
            converged=converged,
            residual=max(point.equilibrium_residual for point in points),
            iterations=iterations,
            warnings=["ChemSep PR parameter applicability requires engineering review."],
            backend_version=self.version,
            solver_name="thermo.FlashVL / PRMIX",
        )

    def tp_flash(self, request: TaskManifest) -> CalculationResult:
        temperature = self._require_temperature(request)
        pressure = self._require_pressure(request)
        feed = self._require_composition(request, "feed_composition")
        solution = self._flash(request, T=temperature, P=pressure * 1000.0, zs=feed)
        return self._result(request, solution)

    def phase_stability(self, request: TaskManifest) -> CalculationResult:
        result = self.tp_flash(request)
        return result.model_copy(
            update={
                "warnings": [
                    *result.warnings,
                    "Phase stability was evaluated by thermo.FlashVL during phase identification.",
                ]
            }
        )

    def azeotrope(self, request: TaskManifest) -> CalculationResult:
        curve = self.isobaric_vle(request)
        candidates = [
            point
            for point in curve.points[1:-1]
            if max(
                abs(liquid - vapor)
                for liquid, vapor in zip(
                    point.liquid_composition,
                    point.vapor_composition,
                    strict=True,
                )
            )
            <= 1e-3
        ]
        message = (
            "No internal azeotrope candidate met |x-y| <= 1e-3."
            if not candidates
            else "Candidate points require local refinement before engineering use."
        )
        return curve.model_copy(update={"points": candidates, "warnings": [*curve.warnings, message]})

    def lle(self, request: TaskManifest) -> CalculationResult:
        raise ThermoEquiError(
            FailureType.UNSUPPORTED_MODEL,
            "The Peng-Robinson adapter is not enabled for LLE in this release.",
            "Use a validated activity-coefficient LLE backend with evidence-bearing parameters.",
        )
