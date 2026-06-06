# CLI Reference

DocSearch is driven through one entry point:

```bash
python -m docsearch.main [options]
```

## Core options

| Flag | Default | Description |
|---|---|---|
| `--module` | *(required)* | The repository directory (repo mode) — or a single source file / module name (with `--dataset-root`). |
| `--target-file` | — | Repo mode: optimize just this one source file (repo-relative or absolute). If omitted, all non-test source files are optimized. |
| `--target-dir` | — | Repo mode: optimize only files under this sub-path. The dependency closure is still built from the whole repo. |
| `--max-files` | `0` | Repo mode: cap how many files are optimized when `--target-file` is omitted (`0` = no cap). |
| `--language` | `python` | `python` or `java`. |

## Search options

| Flag | Default | Description |
|---|---|---|
| `--budget` | *(internal default)* | Maximum number of **outer iterations** (entities refined). |
| `--width` | *(internal default)* | Inner beam width **K** — candidate doc edits explored per iteration. |
| `--debug-budget` | `0` | Max code-debug attempts per node for assertion failures (`0` = disabled). |
| `--no-perturbation` | off | Disable perturbations (use test-error sampling only). |

## Model options

| Flag | Default | Description |
|---|---|---|
| `--hint-model` | `gpt-5.2-us` | Model for diagnosis/prescription and doc assembly. |
| `--code-model` | `gpt-5.2-us` | Model for the code-generation agent. |

Set the matching API key in the environment (`OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY`).

## Test options

| Flag | Default | Description |
|---|---|---|
| `--test-file` | — | Reuse an existing test suite instead of generating one (skips test-gen). |

## Output options

| Flag | Default | Description |
|---|---|---|
| `-o`, `--output` | — | Path to write the final refined document (e.g. `runs/x/refined_doc.md`). |
| `--output-dir` | — | Directory for run artifacts. |
| `--save-artifacts` | off | Persist the search tree, node info, codegen sessions, and the generated suite. **Required to get the `artifacts/` tree.** |
| `--generate-baseline` | off | Generate a baseline doc from the source and exit (or save with `-o`). |
| `--baseline-doc` | — | Use this baseline doc instead of auto-detection. |

## Other

| Flag | Default | Description |
|---|---|---|
| `--dataset-root` | — | Root for resolving `--module` as a module name (legacy/dataset mode). |
| `--resume` | — | Resume from a previous run directory. |
| `--manual-mode` | off | Pause at each entity for the user to supply docs by hand. |

## Recipes

**Optimize one Python file, thorough search, full artifacts:**

```bash
python -m docsearch.main \
    --module /path/to/repo --target-file pkg/util.py \
    --language python --budget 10 --width 2 \
    --save-artifacts --output-dir runs/myrepo -o runs/myrepo/refined_doc.md
```

**Optimize one Java class:**

```bash
python -m docsearch.main \
    --module /path/to/java/repo \
    --target-file src/main/java/org/example/Foo.java \
    --language java --budget 10 --width 2 \
    --save-artifacts --output-dir runs/foo -o runs/foo/refined_doc.md
```

**Reuse an existing suite (skip test-gen) — re-run only the search:**

```bash
python -m docsearch.main \
    --module /path/to/repo --target-file pkg/util.py \
    --test-file /path/to/test_util.py \
    --language python --budget 10 --width 2 \
    --save-artifacts --output-dir runs/myrepo -o runs/myrepo/refined_doc.md
```

**Optimize a whole subtree, capped at 10 files:**

```bash
python -m docsearch.main \
    --module /path/to/repo --target-dir pkg/core --max-files 10 \
    --language python --budget 10 --width 2 \
    --save-artifacts --output-dir runs/core
```
