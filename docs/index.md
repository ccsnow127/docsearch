<p align="center">
  <img src="assets/logo.png" alt="DocSearch logo" width="160" />
</p>

# DocSearch

> Optimize a repository's documentation until an LLM can rebuild its code from
> the docs alone.

DocSearch is a dependency-guided, bi-level search that rewrites a module's
per-entity documentation into **repo-specific playbooks**. The goal is concrete:
a coding agent that reads *only* the documentation should be able to
re-synthesize the module's code and pass a hidden test suite.

It is the system behind the ICML 2026 paper *"Escaping Whack-a-Mole: Optimizing
Documentation as Repo-Specific Playbooks for Coding Agents,"* and a maintained
tool used in production settings.

## The mental model

Most agent reliability work patches prompts one failure at a time. DocSearch
takes the opposite stance: **the documentation is the artifact to optimize, and
the test suite is the oracle.**

For each entity (a function, method, or class) DocSearch asks a simple question:

> If an agent regenerates this entity's code from its current documentation,
> what fraction of its tests pass?

That fraction is **φ (phi)**. DocSearch searches the space of documentation
edits to push φ toward 1.0 across the whole module — while respecting the
call-graph, so improving one entity is never allowed to silently break a caller.

## What's new

- 📦 **[Repo-level input](news/2026-06-repo-level-input.md)** — run directly on
  a raw repository; DocSearch builds the dependency closure and the initial docs
  itself.
- 🟦 **[Java language support](news/2026-06-java-support.md)** — the pipeline now
  speaks Java too (testing, documentation, code generation); validated on jsoup,
  with broader Java coverage in progress.

## Where to go next

| If you want to… | Read |
|---|---|
| Install it and run your first optimization | [Getting Started](getting-started.md) |
| Understand the vocabulary | [Concepts](concepts.md) |
| See how the pipeline and search fit together | [Architecture](architecture.md) |
| Look up a command-line flag | [CLI Reference](cli.md) |
| Know what's Python-specific vs Java-specific | [Language Support](languages.md) |
| See what's new | [Repo-level input](news/2026-06-repo-level-input.md) · [Java support](news/2026-06-java-support.md) |
