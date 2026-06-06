# 📦 Repo-level input: run DocSearch on any repository

*June 2026*

DocSearch now optimizes documentation **directly on a raw repository**. Point it
at a repo, name a file, and it does the rest. This removes the biggest piece of
friction in the old workflow and makes the tool usable on real-world codebases
out of the box.

## What changed

Previously, DocSearch consumed *pre-packaged modules*: a curated folder per
target, each shipping a hand-authored `initial_docs.json` (the starting
documentation) plus tests laid out in a fixed structure. Great for a fixed
benchmark, painful for anything else — every new target meant manual packaging.

Now the loader works at the level of a **repository**:

```bash
python -m docsearch.main \
    --module /path/to/your/repo \
    --target-file pkg/util.py \
    --language python \
    --budget 10 --width 2 \
    --save-artifacts --output-dir runs/myrepo -o runs/myrepo/refined_doc.md
```

Under the hood, DocSearch now:

1. **Builds the dependency closure** (`search/repo_closure.py`) — the slice of
   the repo the target needs to compile/import and to run its tests against the
   real code.
2. **Parses the target file into entities** (`search/module_builder.py`),
   recovering the call-graph among them.
3. **Generates the initial documentation itself** (`docgen/`) from the source —
   no `initial_docs.json` required.

From there the usual bi-level search takes over.

## Before / after

| | Before | After |
|---|---|---|
| **Input** | Pre-packaged module + `initial_docs.json` | Any local repo + a target file |
| **Initial docs** | Hand-authored | Generated from source |
| **Dependencies** | Declared per module | Derived as a closure from the repo |
| **New target effort** | Manual packaging | One command |

## Why it matters

This is what turns DocSearch from a benchmark harness into a tool you can run on
your own service code. You can now sweep whole packages, optimize a single hot
file before shipping, or point it at an unfamiliar dependency to produce
agent-ready documentation — all without touching the repository's layout.

It also sets up everything else: the same closure machinery is what made
**[Java support](2026-06-java-support.md)** tractable, because a Java target's
classpath is just another kind of closure.

→ See [Architecture → Dependency closure](../architecture.md#1-dependency-closure)
for the details.
