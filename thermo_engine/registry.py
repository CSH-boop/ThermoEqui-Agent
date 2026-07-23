"""Deterministic backend registry for phase-equilibrium model adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from schemas.domain import FailureType, TaskManifest
from thermo_engine.backend import ThermodynamicBackend
from thermo_engine.errors import ThermoEquiError
from thermo_engine.ideal import IdealRaoultBackend
from thermo_engine.thermo_backend import ThermoPengRobinsonBackend


@dataclass(frozen=True)
class BackendRegistration:
    canonical_name: str
    aliases: frozenset[str]
    supported_calculations: frozenset[str]
    factory: Callable[[], ThermodynamicBackend]

    def matches(self, model_name: str) -> bool:
        return model_name.casefold() in self.aliases


class ThermodynamicBackendRegistry:
    """Resolve a reviewed model name to one deterministic backend implementation."""

    def __init__(self, registrations: tuple[BackendRegistration, ...]) -> None:
        self.registrations = registrations

    @staticmethod
    def route_task(task: TaskManifest) -> TaskManifest:
        """Apply conservative model defaults only when the caller did not choose one."""
        if task.model_name is not None:
            return task
        if task.equilibrium_type == "LLE":
            raise ThermoEquiError(
                FailureType.MISSING_PARAMETERS,
                "Current production backends cannot represent liquid-liquid equilibrium; "
                "LLE requires an evidence-backed NRTL or UNIQUAC parameter set.",
                "Select NRTL or UNIQUAC and import reviewed binary parameters.",
            )
        pressure = task.conditions.pressure_kPa
        selected = "Peng-Robinson" if pressure is not None and pressure > 500.0 else "Ideal/Raoult"
        return task.model_copy(update={"model_name": selected})

    def resolve(self, task: TaskManifest) -> ThermodynamicBackend:
        requested = self.route_task(task).model_name or "Ideal/Raoult"
        registration = next((item for item in self.registrations if item.matches(requested)), None)
        if registration is None:
            failure_type = (
                FailureType.MISSING_PARAMETERS
                if requested.casefold() in {"wilson", "nrtl", "uniquac"}
                else FailureType.UNSUPPORTED_MODEL
            )
            raise ThermoEquiError(
                failure_type,
                f"Model {requested} has no resolved production parameter set/backend.",
                "Import an evidence-bearing parameter set or choose an available model.",
            )
        if task.calculation_type not in registration.supported_calculations:
            raise ThermoEquiError(
                FailureType.UNSUPPORTED_MODEL,
                f"Model {registration.canonical_name} does not implement {task.calculation_type}.",
                "Choose a calculation supported by the selected model.",
            )
        return registration.factory()


DEFAULT_BACKEND_REGISTRY = ThermodynamicBackendRegistry(
    (
        BackendRegistration(
            canonical_name="Ideal/Raoult",
            aliases=frozenset({"ideal", "raoult", "ideal/raoult"}),
            supported_calculations=frozenset(
                {
                    "bubble_point",
                    "dew_point",
                    "isobaric_vle",
                    "isothermal_vle",
                    "tp_flash",
                    "phase_stability",
                    "azeotrope",
                    "lle",
                }
            ),
            factory=IdealRaoultBackend,
        ),
        BackendRegistration(
            canonical_name="Peng-Robinson",
            aliases=frozenset({"peng-robinson", "peng robinson", "pr"}),
            supported_calculations=frozenset(
                {
                    "bubble_point",
                    "dew_point",
                    "isobaric_vle",
                    "isothermal_vle",
                    "tp_flash",
                    "phase_stability",
                    "azeotrope",
                }
            ),
            factory=ThermoPengRobinsonBackend,
        ),
    )
)
