# Architecture

This page walks through the full pipeline and the bi-level search, then gives a
module-by-module tour of `src/docsearch/`.

## The pipeline

```
            ┌─────────────────────────────────────────────────────────────┐
  raw repo  │  1. dependency closure   (search/repo_closure.py)           │
  ───────▶  │  2. parse target file    (search/module_builder.py)         │
            │  3. ReAct test-gen       (testgen/react/)                    │
            │  4. initial docs         (docgen/)                          │
            │  5. bi-level search      (search/loop.py + inner/outer)     │
            │  6. assemble refined doc (docgen/doc_assembler.py)          │
            └─────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                          refined_doc.md + artifacts/
```

Each stage is independently testable and language-parameterized.

### 1 · Dependency closure

`repo_closure.build_closure` slices the repository down to what the target file
needs to compile/import and to run its tests against the ground-truth code. For
Java this yields a dependency classpath; for Python, the importable package
set. This is the foundation of repo-level input.

### 2 · Module construction

`module_builder.build_module_docs_and_repo` parses the target file into a
`Module` of entities plus the call-graph edges among them, and produces the
parsed repo structure used later for doc assembly.

### 3 · Test generation

A ReAct agent (`testgen/react/`) authors a test suite for the file's entities,
running it against the real source after every edit and fixing failures until
the suite passes. Coverage gates thoroughness (pytest + coverage.py for Python;
Maven + JaCoCo for Java). The suite is the **hidden oracle** the search scores
against. You can skip this stage and reuse an existing suite with `--test-file`.

### 4 · Initial documentation

`docgen/` parses the source (Python `ast`; Java tree-sitter) and generates
per-entity documentation with batched LLM calls, then assembles deterministic
Markdown. This is the starting point — the node the search refines.

### 5 · Bi-level search

The core algorithm. Detailed below.

### 6 · Assembly

`docgen/doc_assembler.py` stitches the best node's per-entity docs back into a
single refined document, written to `-o` and (per file) under `docs/` in the
run directory.

## The bi-level search

`search/loop.py` orchestrates it. After a **bootstrap** (generate code from the
initial docs, evaluate, record the root node), it iterates:

```python
while iterations < budget:
    entity = select_entity(current, module, topo)   # outer: worst-φ, dep-order
    if entity is None:
        break                                        # nothing worth refining
    children = expand(current, entity, ...)          # inner: K candidate edits
    worthy   = first_worthy(current, children, entity)
    iterations += 1
    if worthy is not None:
        current = worthy                             # commit the improvement
    else:
        # all candidates regress a sibling -> record implicit edges,
        # re-topo and retry, or mark the entity intractable
        ...
```

### Outer loop — *which* entity

`select_entity` (`search/outer.py`, `search/topo.py`) walks the module in
**reverse-topological order** so an entity's dependencies are hardened before
its dependents, and picks the lowest-φ candidate. When all entities are at
φ = 1.0 it returns `None` and the search stops early (`iterations = 0` in the
trivial case).

### Inner loop — *how* to edit

`expand` (`search/inner.py`) runs the diagnose/prescribe beam for the chosen
entity:

1. **Sample** diversified batches of the entity's current failures
   (`sample_error_batches`, `batch_size = 3` by default).
2. **Diagnose** the root cause of each batch.
3. **Prescribe** a targeted edit to that entity's documentation.
4. Generate code from the edited docs, **evaluate**, and keep the candidates.

It explores `beam_width` (K = `--width`) candidates per iteration.

### Worthy commits and implicit edges

`first_worthy` (`search/worthy.py`) accepts the first candidate that raises the
target entity's φ without regressing any already-passing sibling. If none
qualify, the regressions themselves are informative: a regressed sibling implies
an **unrecorded dependency** on the refined entity, so DocSearch adds that edge,
recomputes the topological order, and retries — or, failing that, marks the
entity intractable for the branch.

### Code generation and evaluation

The search is parameterized by two injected contracts (`search/contracts.py`):

- **`CodeGenerator`** — `AgentCodeGenerator` (`search/codegen_agent.py`) is a
  ReAct agent that regenerates code from docs with compile/run feedback
  (`javac` for Java, import for Python).
- **`Evaluator`** — `PythonEvaluator` / `JavaEvaluator` (`search/evaluator.py`)
  run the suite and attribute pass/fail to entities, producing the φ vector.

## Module tour

| Path | Responsibility |
|---|---|
| `main.py` | Repo-level CLI; wires closure → testgen → docgen → search → assembly. |
| `agent/` | Generic ReAct director loop (`run_agent`) + filesystem tools, shared by the code/test agents. |
| `llm/` | Unified backends (OpenAI / Anthropic / Gemini), `generate_with_tools`, and `AgentLLM` (`chat_step`). |
| `docgen/` | Python/Java parsers, batched per-entity doc generation, Markdown assembly. |
| `testgen/react/` | ReAct test author + per-language analyzers (pytest/coverage, Maven/JaCoCo). |
| `search/` | The bi-level algorithm: `repo_closure`, `module_builder`, `outer`, `inner`, `worthy`, `loop`, `evaluator`, `codegen_agent`, `topo`, `types`, `contracts`. |
| `pipeline/` | Shared primitives: `entities`, `call_graph`, `topo_sort`, `code_generator`, `evaluator`. |
| `prompts/` | Prompt templates. |
| `utils/` | Metrics (solve_rate / pass_rate, token ledger). |
| `test_executor.py` | pytest runner + per-entity test-name attribution. |
| `java_test_executor.py` | JUnit runner: `javac` compile + console launcher, classpath wiring. |

## Artifacts

With `--save-artifacts`, `main.py` persists the whole trajectory so a run is
fully auditable. The layout is documented in
[Getting Started → Reading the output](getting-started.md#reading-the-output).
