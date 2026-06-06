# Getting Started

This guide takes you from a clean checkout to your first optimized documentation
file.

## Requirements

- **Python ≥ 3.10**
- An API key for one LLM backend: OpenAI, Anthropic, or Google Gemini.
- **For Java targets only:** a JDK (`java`, `javac`) and Maven on your `PATH`.

## Install

```bash
git clone git@github.com:ccsnow127/docsearch.git
cd docsearch
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

This installs the `docsearch` package and its dependencies (pytest, coverage,
the LLM SDKs, and the tree-sitter / `javalang` parsers used by the Java path).

## Configure a model

Export the key for whichever backend you'll use:

```bash
export OPENAI_API_KEY=sk-...
# or
export ANTHROPIC_API_KEY=sk-ant-...
# or
export GOOGLE_API_KEY=...
```

Select models per run with `--hint-model` (used for diagnosis/prescription and
doc assembly) and `--code-model` (used by the code-generation agent).

## Your first run

DocSearch optimizes the documentation of a **single source file inside a real
repository**. Point `--module` at the repo and `--target-file` at the file
(repo-relative):

```bash
python -m docsearch.main \
    --module /path/to/your/repo \
    --target-file pkg/util.py \
    --language python \
    --budget 10 --width 2 \
    --hint-model gpt-5.2-us --code-model gpt-5.2-us \
    --save-artifacts --output-dir runs/myrepo \
    -o runs/myrepo/refined_doc.md
```

What happens, in order:

1. **Dependency closure** — DocSearch resolves what `pkg/util.py` needs so the
   regenerated code compiles/imports against the real repo.
2. **Test generation** — a ReAct agent writes a test suite for the file's
   entities, run against the ground-truth source until it passes.
3. **Initial docs** — per-entity documentation is generated from the source.
4. **Bi-level search** — up to `--budget` outer iterations, each exploring
   `--width` candidate doc edits, committing those that raise φ.
5. **Output** — the refined documentation is written to `-o`, and the full
   trajectory under `--output-dir`.

!!! tip
    Start with a small `--budget 4 --width 1` while you're learning the tool;
    raise to `--budget 10 --width 2` for a thorough search.

## Reading the output

With `--save-artifacts`, the run directory looks like:

```
runs/myrepo/
├── refined_doc.md                      # the final, optimized documentation
├── docs/pkg_util.py.md                 # this file's refined doc, standalone
└── artifacts/
    ├── result.json                     # run-level summary
    └── files/pkg_util.py/
        ├── testgen.json                # what the test-gen produced
        ├── test_util.py                # the generated suite
        ├── testgen_workspace/          # the test-author agent's workspace
        ├── codegen_runs/run_*/         # each code-gen session + its workspace
        │   └── session.jsonl
        ├── nodes/node_*/               # every search node: docs, code, φ, errors
        ├── summary.json                # running best φ + per-entity φ
        └── tree.txt                    # the search tree with φ per node
```

The two files you'll look at most:

- **`summary.json`** — the best mean φ and the per-entity φ breakdown.
- **`tree.txt`** — the shape of the search; did it find anything to refine?

A `best mean φ=1.000  iterations=0` means the initial documentation already let
the agent reproduce correct code — there was nothing to refine. Lower initial φ
is where the search earns its keep.

## Next steps

- The vocabulary behind φ and "worthy" commits: [Concepts](concepts.md).
- The full flag list: [CLI Reference](cli.md).
- Java specifics: [Language Support](languages.md).
