"""Entity and module representations used across the pipeline.

An entity is a callable unit (top-level function, class, or method)
identified by a qualified name, plus its signature, source, and the
documentation string being optimized.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EntityKind(str, Enum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"


@dataclass(frozen=True)
class Entity:
    """Identifier + static info. Runtime state (current doc, generated
    code, pass rate) lives on the search-tree node, not the entity."""

    qualname: str
    kind: EntityKind
    signature: str = ""
    source: str = ""
    # Class-level declared field lines (Java white-box interface contract);
    # empty for functions/methods. Additive -- does not affect the phi signal.
    fields: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        # Java constructors are named "ClassName constructor".
        if " constructor" in self.qualname:
            return self.qualname
        return self.qualname.rsplit(".", 1)[-1]


@dataclass
class Module:
    """A code module: a set of entities with a directed call graph.

    ``source`` holds the full original module source so test validation
    can run against the real reference (module-level constants,
    imports, etc.), not a stitched-together entity-only synthesis.
    """

    name: str
    entities: dict[str, Entity] = field(default_factory=dict)
    edges: set[tuple[str, str]] = field(default_factory=set)  # (caller, callee)
    source: str = ""
    language: str = "python"  # "python" | "java"

    def add_entity(self, e: Entity) -> None:
        self.entities[e.qualname] = e

    def add_edge(self, caller: str, callee: str) -> None:
        if caller in self.entities and callee in self.entities:
            self.edges.add((caller, callee))

    def callees_of(self, qualname: str) -> set[str]:
        return {c for (a, c) in self.edges if a == qualname}

    def callers_of(self, qualname: str) -> set[str]:
        return {a for (a, c) in self.edges if c == qualname}
