"""Outer-level entity selection."""
from __future__ import annotations

from typing import Optional

from docsearch.pipeline.entities import Module
from docsearch.search.types import Node


def select_entity(
    node: Node,
    module: Module,
    topological_order: list[str],
) -> Optional[str]:
    """Pick the next entity to refine, or ``None`` if nothing is eligible.

    ``topological_order`` is a reverse-topo flattening of the dependency
    DAG (callees first). Iterating in that order means an entity is
    visited only after all its callees.

    The function honours both ``node.solved`` and ``node.intractable``;
    entities in either set are not candidates.

    An entity that is absent from ``node.phi`` has no tests (it is unmeasured),
    so there is no signal to refine it against. Such entities are ineligible --
    this is distinct from ``intractable`` (which means we measured it and could
    not improve it). Skipping them keeps the search focused on tested entities.
    """
    solved = node.solved
    intractable = node.intractable
    tested = set(node.phi)  # entities that actually have tests (measured)

    eligible: list[str] = []
    for qn in topological_order:
        if qn in solved or qn in intractable:
            continue
        if qn not in node.phi:
            # No tests / unmeasured: no signal to improve, so not a candidate.
            continue
        # Reverse-topo gating: a callee should be resolved before its caller.
        # But ONLY tested callees can gate — an untested callee has no signal,
        # can never become "solved", and must not permanently block its callers
        # (otherwise selection deadlocks and the search never refines anything).
        blocking = (module.callees_of(qn) & tested) - solved - intractable
        if not blocking:
            eligible.append(qn)

    if not eligible:
        return None

    # Prioritise siblings with the fewest failing tests.
    def failing_count(q: str) -> int:
        return len(node.failures.get(q, []))

    return min(
        eligible,
        key=lambda q: (failing_count(q), topological_order.index(q)),
    )
