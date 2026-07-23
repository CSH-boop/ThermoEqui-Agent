"""Independent component-identity resolution for Agent task grounding."""

from __future__ import annotations

import re
from functools import lru_cache

from chemicals.elements import simple_formula_parser
from chemicals.identifiers import CAS_to_int, search_chemical
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
    "for",
    "flash",
    "fraction",
    "from",
    "in",
    "include",
    "into",
    "liquid",
    "model",
    "mole",
    "molar",
    "phase",
    "point",
    "pressure",
    "result",
    "temperature",
    "the",
    "to",
    "use",
    "using",
    "vapor",
    "with",
}
_CAS_PATTERN = re.compile(r"(?<!\d)(\d{2,7}-\d{2}-\d)(?!\d)")
_NAME_PATTERN = re.compile(r"(?<![A-Za-z0-9])((?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)(?![A-Za-z0-9])")
_MAX_NAME_WORDS = 4
_CURATED_UNAMBIGUOUS_ALIASES = {
    "2 propanol": "67-63-0",
    "isopropyl alcohol": "67-63-0",
    "ethyl alcohol": "64-17-5",
    "n hexane": "110-54-3",
    "r134a": "811-97-2",
}
_ELECTROLYTE_NAME_PATTERN = re.compile(
    r"^(?:ammonium\b|hydrochloric acid$|hydrobromic acid$|hydroiodic acid$|"
    r"hydrofluoric acid$|sulfuric acid$|nitric acid$|phosphoric acid$|perchloric acid$)",
    re.IGNORECASE,
)
_CURATED_ELECTROLYTE_CAS = {
    "67-48-1",  # choline chloride
    "75-57-0",  # tetramethylammonium chloride
    "127-08-2",  # potassium acetate
    "127-09-3",  # sodium acetate
    "1066-33-7",  # ammonium bicarbonate
    "1310-58-3",  # potassium hydroxide
    "1310-73-2",  # sodium hydroxide
    "144-55-8",  # sodium bicarbonate
    "1643-19-2",  # tetrabutylammonium bromide
    "7447-40-7",  # potassium chloride
    "7647-01-0",  # hydrochloric acid
    "7647-14-5",  # sodium chloride
    "7664-93-9",  # sulfuric acid
    "7705-08-0",  # ferric chloride
    "7758-98-7",  # copper sulfate
    "12265-14-4",  # phosphonium chloride
}


@lru_cache(maxsize=512)
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


def _canonical_name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _is_verified_alias(literal: str, resolved: ComponentIdentity) -> bool:
    if resolved.cas_number is None:
        return False
    try:
        metadata = search_chemical(literal)
    except (ValueError, LookupError, TypeError):
        return False
    if metadata.CAS != CAS_to_int(resolved.cas_number):
        return False
    literal_key = _canonical_name_key(literal)
    canonical_keys = {
        _canonical_name_key(name) for name in (metadata.common_name, metadata.iupac_name, resolved.name) if name
    }
    formula_matches = False
    if re.fullmatch(r"(?:[A-Z][a-z]?\d*)+", literal):
        try:
            formula_matches = simple_formula_parser(literal) == simple_formula_parser(metadata.formula)
        except (ValueError, TypeError):
            formula_matches = False
    return (
        literal_key in canonical_keys
        or _CURATED_UNAMBIGUOUS_ALIASES.get(literal_key) == resolved.cas_number
        or formula_matches
    )


def _has_negated_chemical_role(message: str, start: int) -> bool:
    prefix = message[max(0, start - 64) : start].casefold()
    return (
        re.search(
            r"(?:without|excluding|exclude|free\s+of|with\s+no|do\s+not\s+(?:include|add|use)|"
            r"不含|排除|不要|不包括)[^,;.!?。！？]{0,40}$",
            prefix,
        )
        is not None
    )


def has_chemical_role_evidence(message: str, start: int, end: int) -> bool:
    prefix = message[max(0, start - 64) : start].casefold()
    suffix = message[end : min(len(message), end + 48)].casefold()
    if _has_negated_chemical_role(message, start):
        return False
    if re.match(r"\s+(?:time|loss(?:es)?|usage|standard|effects?|record(?:ed|s)?)\b", suffix):
        return False
    before = re.search(
        r"(?:(?:calculate|compute|simulate|evaluate)\s+(?:(?:a|the)\s+)?"
        r"(?:(?:(?:salt|brine|saltwater)[-\s]?free|non[-\s]?ionic)\s+)?|"
        r"(?:bubble\s+point|dew\s+point|(?:tp\s+)?flash|vle|azeotrope|equilibrium|"
        r"mixture|system|components?)\s+(?:of|for)\s+(?:the\s+)?|"
        r"(?:use|using)\s+[a-z0-9-]+\s+for\s+(?:the\s+)?|"
        r"(?:mixture|system|components?)\s+(?:containing|contains|with)\s+(?:the\s+)?|"
        r"计算|模拟|物系|组分|含)\s*$",
        prefix,
    )
    after = re.match(
        r"\s*(?:and\b|with\b|at\b|(?:tp\s*)?flash\b|bubble\b|dew\b|vle\b|"
        r"azeotrope\b|equilibrium\b|composition\b|t-x-y\b|p-x-y\b|"
        r"和|与|、|在|的|常压|汽液|液液|泡点|露点|相平衡|曲线|闪蒸)",
        suffix,
    )
    return before is not None or after is not None


def is_electrolyte_identity(component: ComponentIdentity) -> bool:
    """Return whether a resolved component is a supported-scope electrolyte salt."""
    if component.cas_number is None:
        return False
    try:
        metadata = search_chemical(component.cas_number)
    except (ValueError, LookupError, TypeError):
        return False
    is_registered = component.cas_number in _CURATED_ELECTROLYTE_CAS
    is_charged = bool(metadata.charge)
    is_curated_electrolyte = _ELECTROLYTE_NAME_PATTERN.search(component.name.strip()) is not None
    return is_registered or is_charged or is_curated_electrolyte


def _is_component_list_separator(value: str) -> bool:
    return re.fullmatch(r"\s*(?:(?:,\s*)?(?:and|with)\b|,|/|\+)\s*", value.casefold()) is not None


def _has_scoped_list_role_evidence(message: str, start: int, end: int) -> bool:
    prefix = message[max(0, start - 80) : start].casefold()
    suffix = message[end:].casefold()
    scoped_prefix = re.search(
        r"(?:(?:calculate|compute|simulate|evaluate)\s+(?:(?:a|the)\s+)?"
        r"(?:(?:tp\s+)?flash|vle|bubble\s+point|dew\s+point|azeotrope|equilibrium)?\s*"
        r"(?:for|of)?|(?:use|using)\s+[a-z0-9-]+\s+for)\s*$",
        prefix,
    )
    complete_suffix = re.fullmatch(r"\s*(?:[.!?。！？]\s*)?", suffix)
    return scoped_prefix is not None and complete_suffix is not None


def resolve_literal_components(message: str) -> list[tuple[int, ComponentIdentity]]:
    """Resolve literal identities using longest verified-name spans and CAS numbers."""
    candidates: list[tuple[int, int, str, bool]] = [
        (match.start(1), match.end(1), match.group(1), True) for match in _CAS_PATTERN.finditer(message)
    ]
    name_matches = list(_NAME_PATTERN.finditer(message))
    for start_index, first in enumerate(name_matches):
        if first.group(1).casefold() in _NON_COMPONENT_TERMS:
            continue
        for end_index in range(start_index, min(len(name_matches), start_index + _MAX_NAME_WORDS)):
            last = name_matches[end_index]
            words = [match.group(1) for match in name_matches[start_index : end_index + 1]]
            if any(word.casefold() in _NON_COMPONENT_TERMS for word in words):
                break
            if end_index > start_index:
                gap = message[name_matches[end_index - 1].end(1) : last.start(1)]
                if not gap.isspace():
                    break
            literal = " ".join(words)
            if len(literal) >= 3:
                candidates.append((first.start(1), last.end(1), literal, False))

    verified_spans: list[tuple[int, int, ComponentIdentity, bool]] = []
    for start, end, literal, is_cas in candidates:
        resolved = resolve_external_component(literal)
        if resolved is None or resolved.cas_number is None:
            continue
        if _has_negated_chemical_role(message, start):
            continue
        if not is_cas and not _is_verified_alias(literal, resolved):
            continue
        verified_spans.append((start, end, resolved, is_cas))

    selected: list[tuple[int, int, ComponentIdentity, bool]] = []
    for start, end, resolved, is_cas in sorted(
        verified_spans,
        key=lambda item: (-(item[1] - item[0]), item[0]),
    ):
        if any(start < selected_end and end > selected_start for selected_start, selected_end, _, _ in selected):
            continue
        selected.append((start, end, resolved, is_cas))

    selected.sort(key=lambda item: item[0])
    grounded_indexes = {
        index
        for index, (start, end, _, is_cas) in enumerate(selected)
        if has_chemical_role_evidence(message, start, end)
    }
    group_start = 0
    for index in range(len(selected)):
        group_ends = index == len(selected) - 1 or not _is_component_list_separator(
            message[selected[index][1] : selected[index + 1][0]]
        )
        if not group_ends:
            continue
        endpoints_are_grounded = group_start in grounded_indexes and index in grounded_indexes
        group_is_scoped = _has_scoped_list_role_evidence(
            message,
            selected[group_start][0],
            selected[index][1],
        )
        if index > group_start and (endpoints_are_grounded or group_is_scoped):
            grounded_indexes.update(range(group_start, index + 1))
        group_start = index + 1

    resolved_by_cas: dict[str, tuple[int, ComponentIdentity]] = {}
    for index, (position, _, resolved, _) in enumerate(selected):
        if index not in grounded_indexes:
            continue
        assert resolved.cas_number is not None
        current = resolved_by_cas.get(resolved.cas_number)
        if current is None or position < current[0]:
            resolved_by_cas[resolved.cas_number] = (position, resolved)
    return sorted(resolved_by_cas.values(), key=lambda item: item[0])
