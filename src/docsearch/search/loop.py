"""Main search loop: outer entity selection, inner beam, worthy commit.

The loop is decoupled from code generation and evaluation: it drives the
search over an injected :class:`~docsearch.search.contracts.CodeGenerator`
and :class:`~docsearch.search.contracts.Evaluator`. ``phi`` is measured
solely by the evaluator on the hidden suite; the generator's feedback is
compile/smoke only and never sees those tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from docsearch.search.contracts import CodeGenerator, Evaluator
from docsearch.search.inner import InnerConfig, expand
from docsearch.pipeline.entities import Module
from docsearch.search.outer import select_entity
from docsearch.search.topo import flatten_order, reverse_topological_order
from docsearch.search.types import Node, create_root
from docsearch.search.worthy import first_worthy


@dataclass
class SearchConfig:
    budget: int = 50  # max outer iterations
    inner: InnerConfig = field(default_factory=InnerConfig)
    initial_temperature: float = 0.0  # determinism for the bootstrap eval


@dataclass
class SearchResult:
    best_node: Node
    root: Node
    iterations: int
    intractable: list[str]
    implicit_edges_discovered: list[tuple[str, str]]


def run_search(
    module: Module,
    initial_docs: dict[str, str],
    codegen: CodeGenerator,
    evaluator: Evaluator,
    llm,
    *,
    config: SearchConfig | None = None,
    on_step: Optional[Callable[[Node, str], None]] = None,
) -> SearchResult:
    """Run DocSearch end-to-end.

    ``codegen`` synthesizes code from docs; ``evaluator`` scores it on the
    hidden suite; ``llm`` drives the inner diagnose/prescribe stages.

    ``on_step(node, event)`` is an optional callback fired after every
    notable transition (``"bootstrap"``, ``"commit"``, ``"intractable"``,
    ``"topo_refresh"``, ``"done"``) so the caller can persist artifacts.
    """
    cfg = config or SearchConfig()

    # 1) Bootstrap: generate code from the initial docs and evaluate.
    root_code = codegen.generate(module, initial_docs)
    root_eval = evaluator.evaluate(root_code)
    root = create_root(
        initial_docs,
        code=root_code,
        phi=root_eval.to_phi_dict(),
        failures={q: r.failures for q, r in root_eval.per_entity.items()},
    )
    if on_step:
        on_step(root, "bootstrap")

    current = root
    implicit_edges: list[tuple[str, str]] = []
    topo_components = reverse_topological_order(module)
    topo = flatten_order(topo_components)
    iterations = 0

    while iterations < cfg.budget:
        entity = select_entity(current, module, topo)
        if entity is None:
            break

        children = expand(
            current,
            entity,
            module,
            codegen,
            evaluator,
            llm,
            config=cfg.inner,
        )
        # Record EVERY explored candidate (its docs, generated code, and phi),
        # not just the committed one, so each iteration's full beam is auditable.
        if on_step:
            for child in children:
                on_step(child, "candidate")
        worthy = first_worthy(current, children, entity)
        iterations += 1

        if worthy is not None:
            current = worthy
            if on_step:
                on_step(current, "commit")
        else:
            # All candidates regress something. Record any implicit edges
            # they revealed (any regressed sibling => unrecorded dep on
            # the refined entity), then mark the entity intractable for
            # this branch.
            edges_before = len(implicit_edges)
            for child in children:
                for e, phi_before in current.phi.items():
                    if e == entity:
                        continue
                    if child.phi.get(e, 0.0) < phi_before:
                        edge = (e, entity)
                        if edge not in module.edges:
                            module.add_edge(e, entity)
                            implicit_edges.append(edge)
            if len(implicit_edges) > edges_before:
                # Topo order may have changed; recompute and *retry* the
                # same entity in the next loop iteration (don't mark
                # intractable yet — give the new ordering a chance).
                topo_components = reverse_topological_order(module)
                topo = flatten_order(topo_components)
                if on_step:
                    on_step(current, "topo_refresh")
                continue

            new_intractable = set(current.intractable) | {entity}
            current = Node(
                docs=dict(current.docs),
                code=current.code,
                phi=dict(current.phi),
                failures=dict(current.failures),
                intractable=new_intractable,
                parent=current,
            )
            current.parent.children.append(current)  # link as child
            if on_step:
                on_step(current, "intractable")

    if on_step:
        on_step(current, "done")

    return SearchResult(
        best_node=current,
        root=root,
        iterations=iterations,
        intractable=sorted(current.intractable),
        implicit_edges_discovered=implicit_edges,
    )
