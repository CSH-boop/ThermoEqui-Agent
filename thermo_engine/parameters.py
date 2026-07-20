"""Explicit parameter direction transformations."""

from __future__ import annotations


def reverse_binary_parameter_direction(
    parameters: dict[str, float], directional_pairs: list[tuple[str, str]]
) -> dict[str, float]:
    """Reverse named directional pairs without guessing a model's parameter form."""
    reversed_parameters = dict(parameters)
    for forward, reverse in directional_pairs:
        if forward not in parameters or reverse not in parameters:
            raise ValueError(f"Directional pair {forward}/{reverse} is incomplete")
        reversed_parameters[forward] = parameters[reverse]
        reversed_parameters[reverse] = parameters[forward]
    return reversed_parameters
