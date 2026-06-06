"""Inner-level beam search: W diagnose-then-prescribe candidates per entity.

The inner level is decoupled from how code is generated and evaluated: it
calls the injected :class:`~docsearch.search.contracts.CodeGenerator` and
:class:`~docsearch.search.contracts.Evaluator` collaborators rather than any
concrete pipeline. ``phi`` is measured by the evaluator on the hidden suite;
the code generator never sees those tests.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from docsearch.search.contracts import CodeGenerator, Evaluator
from docsearch.pipeline.entities import Module
from docsearch.search.prompts import render
from docsearch.search.types import Node


@dataclass
class InnerConfig:
    beam_width: int = 4
    batch_size: int = 3  # size of each diversified error batch
    temperature: float = 0.8
    seed: int | None = 0  # base seed; per-batch seeds are derived from it


# ---------------------------------------------------------------------------
# Diversified error batch sampling
# ---------------------------------------------------------------------------

def sample_error_batches(
    failing_errors: list[str],
    *,
    width: int,
    batch_size: int,
    rng: random.Random,
) -> list[list[str]]:
    """Return ``width`` distinct error batches.

    Each batch is a random subset of ``failing_errors`` of size up to
    ``batch_size``. Batches are guaranteed *pairwise distinct* (as sets)
    when the input has enough variety; otherwise we fall back to drawing
    overlapping subsets with different random orderings.
    """
    if not failing_errors:
        return [[] for _ in range(width)]

    n = len(failing_errors)
    k = min(batch_size, n)

    batches: list[list[str]] = []
    seen: set[frozenset[str]] = set()
    attempts = 0
    max_attempts = width * 10
    while len(batches) < width and attempts < max_attempts:
        attempts += 1
        subset = rng.sample(failing_errors, k)
        sig = frozenset(subset)
        if sig in seen and len(seen) < width:
            continue
        seen.add(sig)
        batches.append(subset)

    # Fall back: pad with overlapping subsets (re-shuffled) if we ran out
    # of distinct combinations.
    while len(batches) < width:
        s = list(failing_errors)
        rng.shuffle(s)
        batches.append(s[:k])

    return batches


# ---------------------------------------------------------------------------
# Two-stage diagnose -> prescribe
# ---------------------------------------------------------------------------

def diagnose(
    *,
    entity_name: str,
    entity_type: str,
    language: str,
    current_doc: str,
    generated_code: str,
    error_batch: list[str],
    llm,
    temperature: float,
    seed: int | None,
) -> str:
    prompt = render(
        "diagnosis",
        language=language,
        entity_name=entity_name,
        entity_type=entity_type,
        current_doc=current_doc,
        generated_code=generated_code,
        error_messages="\n".join(f"- {e}" for e in error_batch) or "(no errors recorded)",
    )
    return llm.complete(prompt, temperature=temperature, seed=seed).text


def prescribe(
    *,
    entity_name: str,
    entity_type: str,
    language: str,
    current_doc: str,
    diagnosis_output: str,
    llm,
    temperature: float,
    seed: int | None,
) -> str:
    prompt = render(
        "prescription",
        language=language,
        entity_name=entity_name,
        entity_type=entity_type,
        current_doc=current_doc,
        diagnosis_output=diagnosis_output,
    )
    return llm.complete(prompt, temperature=temperature, seed=seed).text.strip()


# ---------------------------------------------------------------------------
# Beam expansion
# ---------------------------------------------------------------------------

def expand(
    parent: Node,
    entity: str,
    module: Module,
    codegen: CodeGenerator,
    evaluator: Evaluator,
    llm,
    *,
    config: InnerConfig,
) -> list[Node]:
    """Generate ``config.beam_width`` candidate child nodes.

    For each diversified error batch the inner level (1) diagnoses the
    failure, (2) prescribes a refined doc, (3) asks the injected
    ``codegen`` to synthesize code from the new docs, and (4) scores it
    with the injected ``evaluator``.

    Candidates are produced sequentially; "parallel" refers to logically
    independent beam branches, not OS threads. LLM-call latency
    dominates anyway.
    """
    entity_obj = module.entities[entity]
    language = module.language
    current_doc = parent.docs.get(entity, "")
    failing = parent.failures.get(entity, [])
    rng = random.Random(config.seed)
    batches = sample_error_batches(
        failing, width=config.beam_width, batch_size=config.batch_size, rng=rng
    )

    children: list[Node] = []
    for i, batch in enumerate(batches):
        # Derive a per-batch seed so each beam branch is reproducible yet
        # diversified.
        batch_seed = None if config.seed is None else config.seed + i
        diag = diagnose(
            entity_name=entity,
            entity_type=entity_obj.kind.value,
            language=language,
            current_doc=current_doc,
            generated_code=parent.code,
            error_batch=batch,
            llm=llm,
            temperature=config.temperature,
            seed=batch_seed,
        )
        new_doc = prescribe(
            entity_name=entity,
            entity_type=entity_obj.kind.value,
            language=language,
            current_doc=current_doc,
            diagnosis_output=diag,
            llm=llm,
            temperature=config.temperature,
            seed=batch_seed,
        )

        new_docs = dict(parent.docs)
        new_docs[entity] = new_doc

        new_code = codegen.generate(module, new_docs)
        eval_result = evaluator.evaluate(new_code)
        child = Node(
            docs=new_docs,
            code=new_code,
            phi=eval_result.to_phi_dict(),
            failures={q: r.failures for q, r in eval_result.per_entity.items()},
            refined_entity=entity,
            intractable=set(parent.intractable),
        )
        parent.add_child(child)
        children.append(child)
    return children
