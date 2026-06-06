# Concepts

A short glossary of the ideas DocSearch is built on. Skim it once and the rest
of the docs (and the code) read much more easily.

## Entity

The unit of documentation and the unit of measurement. An **entity** is a
function, a method, or a class — anything that has its own behavior and its own
tests. In Python an entity qualname looks like `next_weekday` (a free function)
or `Renko.period_close_bricks` (a method). In Java, `Collector.collect`.

DocSearch documents *every* entity in the target file and tracks a φ for each.

## Module

The set of entities parsed out of one target file, together with the call-graph
**edges** between them. The module is what a single optimization run operates
on; `build_module_docs_and_repo` constructs it.

## Dependency closure

To regenerate an entity's code and actually run its tests, the surrounding repo
has to be present — imports, helper classes, the dependency classpath (Java) or
importable packages (Python). The **closure** (`docsearch.search.repo_closure`)
is the slice of the repo needed for the target to compile/import and its tests
to run against the ground truth. This is what makes **repo-level input**
possible: DocSearch derives the closure from the raw repository instead of
relying on a pre-packaged module.

## φ (phi) — the signal

The heart of the system. For an entity *e*:

> **φ(e)** = the fraction of *e*'s tests that pass when an agent regenerates
> *e*'s code **from its documentation alone**.

φ = 1.0 means the documentation is a sufficient playbook: the agent rebuilds
correct code. φ = 0.0 means the docs leave the agent guessing. The **mean φ**
over a module's tested entities is the score the search maximizes.

φ is grounded in a real test run, attributed per entity by mapping each test
back to the entity it exercises. It is *not* an LLM self-rating.

## Node

One state in the search: a complete set of per-entity docs, the code an agent
generated from them, and the resulting φ vector. The search starts from a
**root** node (initial docs) and explores **child** nodes that differ by a
documentation edit to one entity.

## Worthy commit

A candidate child node is **worthy** only if it raises the target entity's φ
**without regressing any already-passing sibling**. This is the call-graph
discipline: improving `parse` is not allowed to silently break `parse_all` that
depends on it. If every candidate regresses something, the entity is marked
*intractable* for that branch — and any sibling it broke reveals an implicit
dependency edge, which is added to the graph so the search can re-order around
it.

## Outer loop vs inner loop

DocSearch is **bi-level**:

- **Outer loop** decides *which* entity to work on next — the worst-φ entity in
  reverse-topological (dependency) order, so dependencies are solidified before
  their dependents. Its length is bounded by `--budget`.
- **Inner loop** decides *how* to edit that entity's docs — it samples
  diversified batches of the entity's failures, **diagnoses** the root cause,
  and **prescribes** a targeted documentation edit, exploring `--width` (K)
  candidates and keeping the best worthy one.

See [Architecture](architecture.md) for how these compose into a full run.

## Budget and width (K)

- **`--budget`** — the maximum number of outer iterations (entities refined).
- **`--width` / K** — the inner beam width: how many candidate doc edits are
  generated and evaluated per outer iteration.

Bigger numbers mean a more thorough (and more expensive) search. A practical
starting point is `--budget 10 --width 2`.
