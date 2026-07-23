"""Independent component-identity resolution for Agent task grounding."""

from __future__ import annotations

import re

from thermo import ChemicalConstantsPackage

from schemas.domain import ComponentIdentity

_NON_COMPONENT_TERMS = {
    "and",
    "at",
    "bubble",
    "calculate",
    "calculation",
    "composition",
    "dew",
    "equilibrium",
    "flash",
    "fraction",
    "liquid",
    "model",
    "mole",
    "molar",
    "phase",
    "point",
    "pressure",
    "temperature",
    "the",
    "using",
    "vapor",
    "with",
}
_CAS_PATTERN = re.compile(r"(?<!\d)(\d{2,7}-\d{2}-\d)(?!\d)")
_NAME_PATTERN = re.compile(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*)(?![A-Za-z0-9])")


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


def resolve_literal_components(message: str) -> list[tuple[int, ComponentIdentity]]:
    """Resolve literal English names or CAS numbers present in the user message."""
    candidates: list[tuple[int, str]] = [(match.start(1), match.group(1)) for match in _CAS_PATTERN.finditer(message)]
    candidates.extend(
        (match.start(1), match.group(1))
        for match in _NAME_PATTERN.finditer(message)
        if len(match.group(1)) >= 3 and match.group(1).casefold() not in _NON_COMPONENT_TERMS
    )
    resolved_by_cas: dict[str, tuple[int, ComponentIdentity]] = {}
    for position, literal in candidates:
        resolved = resolve_external_component(literal)
        if resolved is None or resolved.cas_number is None:
            continue
        current = resolved_by_cas.get(resolved.cas_number)
        if current is None or position < current[0]:
            resolved_by_cas[resolved.cas_number] = (position, resolved)
    return sorted(resolved_by_cas.values(), key=lambda item: item[0])
