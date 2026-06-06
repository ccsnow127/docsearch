"""Reverse topological order with Tarjan SCC contraction.

Reverse topological order means *callees before callers*: an entity is
yielded only after every entity it depends on has been yielded.

Cyclic call graphs contract each strongly connected component into a
single meta-entity (a frozen set of qualnames); the outer loop then
refines all members of the SCC jointly.

This module is language-agnostic: it operates only on ``Module.edges``.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from docsearch.pipeline.entities import Module

Component = frozenset[str]


def strongly_connected_components(module: Module) -> list[Component]:
    """Tarjan's SCC algorithm.

    Returns components in reverse topological order over the condensation
    DAG (so the first component listed has no callees outside itself).
    """
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    result: list[Component] = []

    adj: dict[str, list[str]] = defaultdict(list)
    for (caller, callee) in module.edges:
        adj[caller].append(callee)

    def strongconnect(v: str) -> None:
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True

        for w in adj.get(v, ()):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif on_stack.get(w, False):
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            component: list[str] = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                component.append(w)
                if w == v:
                    break
            result.append(frozenset(component))

    for v in module.entities:
        if v not in index:
            strongconnect(v)

    return result


def condensation_edges(
    module: Module, components: list[Component]
) -> tuple[dict[str, Component], set[tuple[Component, Component]]]:
    """Build the DAG over SCCs.

    Returns ``(entity_to_component, edges)`` where ``edges`` contains
    ``(caller_scc, callee_scc)`` for every cross-SCC call.
    """
    e2c: dict[str, Component] = {}
    for c in components:
        for q in c:
            e2c[q] = c

    edges: set[tuple[Component, Component]] = set()
    for (caller, callee) in module.edges:
        ca, cb = e2c[caller], e2c[callee]
        if ca is not cb:
            edges.add((ca, cb))
    return e2c, edges


def reverse_topological_order(module: Module) -> list[Component]:
    """Components (callees first) for the outer loop.

    Tarjan already emits SCCs in reverse-topo order; we re-sort
    deterministically by the alphabetically-smallest member of each
    component (sinks first).
    """
    components = strongly_connected_components(module)
    _, scc_edges = condensation_edges(module, components)

    # Kahn over the condensation, popping sinks (no outgoing edges) first.
    indeg: dict[Component, int] = {c: 0 for c in components}
    out_edges: dict[Component, set[Component]] = {c: set() for c in components}
    in_edges: dict[Component, set[Component]] = {c: set() for c in components}
    for ca, cb in scc_edges:
        # In the condensation: ca -> cb (ca calls cb).
        # We want callees (cb) first, so treat cb as predecessor.
        out_edges[ca].add(cb)
        in_edges[cb].add(ca)
        indeg[ca] += 1  # "depth" from a sink standpoint

    # Sinks: components with no outgoing call edges.
    sinks = [c for c in components if indeg[c] == 0]
    sinks.sort(key=_component_key)

    order: list[Component] = []
    while sinks:
        c = sinks.pop(0)
        order.append(c)
        for parent in sorted(in_edges[c], key=_component_key):
            indeg[parent] -= 1
            if indeg[parent] == 0:
                # insert keeping sorted order
                _insort(sinks, parent)

    if len(order) != len(components):  # pragma: no cover
        raise RuntimeError("topological sort failed; condensation is not a DAG")
    return order


def _component_key(c: Component) -> str:
    return min(c)


def _insort(seq: list[Component], item: Component) -> None:
    key = _component_key(item)
    for i, existing in enumerate(seq):
        if key < _component_key(existing):
            seq.insert(i, item)
            return
    seq.append(item)


def flatten_order(components: Iterable[Component]) -> list[str]:
    """Flatten an SCC order to a per-entity order (members sorted)."""
    flat: list[str] = []
    for c in components:
        flat.extend(sorted(c))
    return flat
