"""Worthy condition: a refinement is worthy iff it regresses no solved entity."""
from __future__ import annotations

from dataclasses import dataclass

from docsearch.search.types import Node


_EPS = 1e-9


@dataclass(frozen=True)
class WorthyVerdict:
    """Worthy if no regression. Also reports newly-discovered implicit
    edges (caller -> callee) that the worthy check uncovered."""

    worthy: bool
    refined_entity: str
    regressions: tuple[str, ...] = ()
    target_improved: bool = False

    def __bool__(self) -> bool:  # `if is_worthy(...)`
        return self.worthy


def is_worthy(parent: Node, child: Node, refined_entity: str) -> WorthyVerdict:
    """Test whether ``child`` regresses any of ``parent``'s solved entities.

    The refined entity itself is excluded from the regression check; a
    transient drop on the refinement target is acceptable while the
    search is exploring it. ``target_improved`` separately reports
    whether the target's own pass rate moved up.
    """
    regressions: list[str] = []
    for e, phi_parent in parent.phi.items():
        if e == refined_entity:
            continue
        phi_child = child.phi.get(e, 0.0)
        if phi_child + _EPS < phi_parent:
            regressions.append(e)

    target_parent = parent.phi.get(refined_entity, 0.0)
    target_child = child.phi.get(refined_entity, 0.0)
    target_improved = target_child + _EPS > target_parent

    return WorthyVerdict(
        worthy=not regressions,
        refined_entity=refined_entity,
        regressions=tuple(sorted(regressions)),
        target_improved=target_improved,
    )


def first_worthy(
    parent: Node, candidates: list[Node], refined_entity: str
) -> Node | None:
    """Return the first child satisfying the worthy condition, or ``None``."""
    for child in candidates:
        if is_worthy(parent, child, refined_entity):
            return child
    return None
