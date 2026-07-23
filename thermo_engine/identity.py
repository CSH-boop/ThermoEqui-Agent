"""Independent component-identity resolution for Agent task grounding."""

from __future__ import annotations

from thermo import ChemicalConstantsPackage

from schemas.domain import ComponentIdentity


def resolve_external_component(identifier: str) -> ComponentIdentity | None:
    """Resolve one literal name or CAS through the deterministic property database."""
    try:
        constants, _ = ChemicalConstantsPackage.from_IDs([identifier])
    except (ValueError, LookupError, TypeError):
        return None
    if len(constants.CASs) != 1 or len(constants.names) != 1:
        return None
    cas_number = str(constants.CASs[0])
    name = str(constants.names[0]).title()
    return ComponentIdentity(
        component_id=cas_number,
        name=name,
        cas_number=cas_number,
        aliases=[identifier],
    )
