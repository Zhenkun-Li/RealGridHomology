from __future__ import annotations

from .knot import Knot, SymmetryKind


def uses_even_strong_grading(knot: Knot) -> bool:
    return knot.symmetry_kind is SymmetryKind.STRONGLY_INVERTIBLE and knot.size % 2 == 0


def destabilization_steps(knot: Knot) -> int:
    if knot.symmetry_kind is SymmetryKind.PERIODIC:
        if knot.size % 2 == 0:
            raise ValueError(
                f"Periodic destabilization is not implemented for even grid size {knot.size}."
            )
        return (knot.size - 1) // 2

    if knot.size % 2 == 0:
        return (knot.size - 2) // 2
    return (knot.size - 1) // 2
