# Contributing to DocSearch

Thanks for your interest in DocSearch. It is both an ICML 2026 research artifact
and a maintained engineering tool, so we care a lot about keeping the codebase
readable, well-documented, and reproducible.

## Ground rules

- **Read like documentation.** Modules and public functions carry docstrings
  that explain *why*, not just *what*. New code should match the surrounding
  density and tone.
- **One pipeline, two languages.** Anything you add to the Python path should
  have a Java counterpart (or a clear reason it doesn't). Keep Java imports
  lazy so the Python path never requires `javalang`/tree-sitter at import time.
- **No silent behavior changes.** If you change attribution, the φ signal, or
  the search loop, say so in the PR.

## Development setup

```bash
git clone git@github.com:ccsnow127/docsearch.git
cd docsearch
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Set an API key (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY`)
before running anything that calls a model. For Java targets you also need a
JDK (`java`, `javac`) and Maven on `PATH`.

## Running

A single-file optimization (the smallest useful end-to-end run):

```bash
python -m docsearch.main \
    --module /path/to/repo --target-file pkg/util.py \
    --language python --budget 4 --width 1 \
    --save-artifacts --output-dir runs/dev -o runs/dev/refined_doc.md
```

Inspect the trajectory under `runs/dev/artifacts/files/<file>/` — `summary.json`
and `tree.txt` are the quickest way to see whether the search behaved.

## Project layout

See the [architecture guide](docs/architecture.md) for a module-by-module tour.
The big pieces are `docgen/`, `testgen/react/`, and `search/`.

## Pull requests

1. Branch from `main`.
2. Keep changes focused; update or add docs under `docs/` when behavior changes.
3. Describe how you verified the change (which command, what the φ/iterations
   looked like before and after).

## Reporting issues

Open a GitHub issue with the command you ran, the `--language`, the model, and
the relevant slice of the run log (strip API keys). If it's a search-quality
issue, attach `summary.json` and `tree.txt` from the run.
