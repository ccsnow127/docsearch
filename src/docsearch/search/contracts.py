"""Shared contracts the search loop depends on.

The bi-level search algorithm is deliberately decoupled from *how* code is
generated and *how* it is evaluated, so the same algorithm runs for Python and
Java. Two injected collaborators provide those capabilities:

    CodeGenerator.generate(module, docs) -> str
        Synthesize a full implementation of ``module`` from the per-entity
        documentation ``docs`` ALONE. The project default is a ReAct agent
        whose feedback tool is COMPILE/SMOKE ONLY (it must NOT see the
        evaluation tests, or phi collapses to 1.0 and the search loses its
        signal).

    Evaluator.evaluate(code) -> EvaluationResult
        Run the (hidden) test suite against generated ``code`` and report a
        per-entity pass rate. Backed by the project's JavaTestExecutor /
        TestExecutor; the generated code never sees these tests.

``EntityResult`` / ``EvaluationResult`` define the evaluator's expected shape
so the search code (which calls ``result.to_phi_dict()`` and reads
``per_entity[q].failures``) works unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable

from docsearch.pipeline.entities import Module


@dataclass
class EntityResult:
    """Per-entity outcome of one evaluation pass."""

    qualname: str
    passed: int = 0
    failed: int = 0
    errors: int = 0
    failures: list[str] = field(default_factory=list)  # error/failure messages

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors

    @property
    def phi(self) -> float:
        # No tests attributed to this entity => vacuously documented (there is no
        # failing evidence), so phi = 1.0. A genuine reconstruction failure is
        # recorded as an error (errors >= 1 => total >= 1 => phi = 0), so this
        # 1.0 only applies when there is truly nothing to test — never to a
        # compile/setup failure.
        if self.total == 0:
            return 1.0
        return self.passed / self.total


@dataclass
class EvaluationResult:
    """Result of evaluating one (code, tests) pair across all entities."""

    per_entity: dict[str, EntityResult] = field(default_factory=dict)
    setup_error: str | None = None  # syntax/compile error, import failure, crash

    def phi(self, entity: str) -> float:
        return self.per_entity.get(entity, EntityResult(entity)).phi

    def to_phi_dict(self) -> dict[str, float]:
        return {q: r.phi for q, r in self.per_entity.items()}


@runtime_checkable
class Evaluator(Protocol):
    """Runs generated code against the hidden suite -> per-entity pass rates."""

    def evaluate(self, code: str) -> EvaluationResult:
        ...


@runtime_checkable
class CodeGenerator(Protocol):
    """Synthesizes a full implementation of ``module`` from docs alone."""

    def generate(self, module: Module, docs: Mapping[str, str]) -> str:
        ...
