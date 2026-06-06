"""Evaluation metrics: solve rate, average pass rate, solved set."""
from __future__ import annotations

from collections.abc import Mapping


def solve_rate(phi: Mapping[str, float]) -> float:
    """Fraction of entities with ``phi_i == 1``. Empty mapping -> ``0.0``."""
    if not phi:
        return 0.0
    solved = sum(1 for v in phi.values() if v >= 1.0 - 1e-9)
    return solved / len(phi)


def average_pass_rate(phi: Mapping[str, float]) -> float:
    """Mean of ``phi_i`` across all entities. Empty -> ``0.0``."""
    if not phi:
        return 0.0
    return sum(phi.values()) / len(phi)


def solved_set(phi: Mapping[str, float]) -> set[str]:
    """Entities whose pass rate is (essentially) 1.0."""
    return {e for e, v in phi.items() if v >= 1.0 - 1e-9}
