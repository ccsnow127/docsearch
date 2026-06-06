"""Search-tree node: one (docs, code, phi, failures) snapshot."""
from __future__ import annotations

import itertools
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Optional


def solved_set(phi: Mapping[str, float]) -> set[str]:
    """Entities whose pass rate is (essentially) 1.0."""
    return {e for e, v in phi.items() if v >= 1.0 - 1e-9}


_node_id_counter = itertools.count()


@dataclass
class Node:
    """One snapshot of (documentation, generated code, pass rates)."""

    docs: dict[str, str]
    code: str = ""
    phi: dict[str, float] = field(default_factory=dict)
    failures: dict[str, list[str]] = field(default_factory=dict)

    # Search-tree bookkeeping
    parent: Optional["Node"] = field(default=None, repr=False)
    children: list["Node"] = field(default_factory=list, repr=False)
    id: int = field(default_factory=lambda: next(_node_id_counter))

    intractable: set[str] = field(default_factory=set)
    refined_entity: Optional[str] = None  # which entity produced this node

    @property
    def solved(self) -> set[str]:
        return solved_set(self.phi)

    def add_child(self, child: "Node") -> None:
        child.parent = self
        self.children.append(child)

    def path_to_root(self) -> list["Node"]:
        path: list[Node] = []
        n: Node | None = self
        while n is not None:
            path.append(n)
            n = n.parent
        path.reverse()
        return path

    def depth(self) -> int:
        return len(self.path_to_root()) - 1


def create_root(
    docs: dict[str, str],
    *,
    code: str = "",
    phi: dict[str, float] | None = None,
    failures: dict[str, list[str]] | None = None,
) -> Node:
    return Node(
        docs=dict(docs),
        code=code,
        phi=dict(phi or {}),
        failures=dict(failures or {}),
    )
