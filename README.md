<div align="center">

<img src="assets/logo.png" alt="DocSearch logo" width="180" />

# DocSearch

**Optimize a repository's documentation until an LLM can rebuild its code from the docs alone.**

*Good documentation = documentation complete and precise enough to rebuild the code from.*

DocSearch is a dependency-guided, bi-level search that rewrites per-entity
documentation into *repo-specific playbooks* — so a coding agent, conditioned
only on the documentation, re-synthesizes code that passes a hidden test suite.

[![ICML 2026](https://img.shields.io/badge/ICML-2026-b31b1b.svg)](#-citation)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://www.python.org/)
[![Languages: Python · Java](https://img.shields.io/badge/targets-Python%20%C2%B7%20Java-2ea44f.svg)](docs/languages.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](#-license)
[![Docs](https://img.shields.io/badge/docs-read-blue.svg)](docs/index.md)

[**Documentation**](docs/index.md) ·
[**Getting Started**](docs/getting-started.md) ·
[**How it works**](docs/architecture.md) ·
[**News**](#-news) ·
[**Citation**](#-citation)

</div>

---

## 📰 News

- **2026-06 — 🟦 Java language support.** The pipeline now *speaks* Java
  as well as Python — test generation, documentation, and code generation run on
  Java via tree-sitter parsing, Maven + JaCoCo coverage, and `javac`/JUnit
  evaluation. Validated end-to-end on a single-module Maven repo (jsoup);
  broader Java coverage (multi-module / Gradle) is in progress.
  → [read the post](docs/news/2026-06-java-support.md)
- **2026-06 — 📦 Repo-level input.** DocSearch now runs directly on a *raw
  repository* — it builds the dependency closure and generates initial
  documentation itself, instead of requiring pre-packaged modules with
  hand-authored `initial_docs.json`. Point it at any local Python or Java
  repo. → [read the post](docs/news/2026-06-repo-level-input.md)
- **2026 — 🎓 Paper accepted at ICML 2026.** *"Escaping Whack-a-Mole:
  Optimizing Documentation as Repo-Specific Playbooks for Coding Agents."*
  → [cite it](#-citation)

---

## ✨ Why DocSearch

Coding agents fail in *repo-specific* ways: a wrong import path, a missing
fixture, an API used the way the docs imply rather than the way the code
actually behaves. Patching prompts one failure at a time is whack-a-mole.

DocSearch instead treats **documentation as the optimization target**. It
measures, per entity, whether an agent can regenerate that entity's code from
its docs and pass the tests — a signal we call **φ (phi)** — and searches the
space of documentation edits to drive φ up across the whole module, respecting
the call-graph so fixing one entity never silently breaks its callers.

| | |
|---|---|
| 🧠 **Bi-level search** | An outer loop picks *which* entity to improve (worst-φ first, in dependency order); an inner beam diagnoses failures and prescribes targeted doc edits. |
| 📈 **Test-grounded signal** | φ is the real pass-rate of regenerated code against a hidden suite — not an LLM's self-assessment. |
| 🤖 **ReAct agents end-to-end** | Tool-using agents author the tests *and* regenerate the code, with compile/run feedback. |
| 🌐 **Python + Java** | One pipeline, two languages, lazily loaded so the Python path needs no Java deps. |
| 🗂️ **Auditable runs** | Every search node, codegen session, and generated suite is persisted under `runs/<repo>/artifacts/`. |

---

## 🚀 Quickstart

```bash
# 1. Install (Python ≥ 3.10)
pip install -e .

# 2. Provide an API key for your chosen backend
export OPENAI_API_KEY=sk-...        # or ANTHROPIC_API_KEY / GOOGLE_API_KEY

# 3. Optimize the documentation of one file in any local repo
python -m docsearch.main \
    --module /path/to/your/repo \
    --target-file pkg/util.py \
    --language python \
    --budget 10 --width 2 \
    --save-artifacts --output-dir runs/myrepo \
    -o runs/myrepo/refined_doc.md
```

DocSearch will: build the repo's dependency closure → generate a test suite for
`pkg/util.py` → write initial docs → run the bi-level search → save the refined
documentation to `refined_doc.md` and the full trajectory under
`runs/myrepo/artifacts/`.

> **Java?** Same command with `--language java` and a `.java` target. First run
> `scripts/fetch_libs.sh` (downloads the JUnit + JaCoCo jars into `src/libs/`)
> and make sure a JDK and Maven are on `PATH`. The bundled Java benchmark is a
> single repo — **jsoup** — by design; see
> [Language support](docs/languages.md#java) for why.

Full flag reference: [docs/cli.md](docs/cli.md).

---

## 🧠 How it works

```
repo
  │
  ├──▶ build dependency closure
  ├──▶ generate hidden test suite  (ReAct)
  ├──▶ generate initial documentation
  │
  ▼
┌─────────────────── bi-level search ────────────────────┐
│  outer:  select the worst-φ entity (dependency order)  │
│  inner:  diagnose failures → prescribe a doc edit      │
│          (K candidates per step — K = beam width)      │
│  commit: keep an edit only if it raises φ              │
│          without regressing any caller                 │
└───────────────────────────┬────────────────────────────┘
                            ▼
                  refined documentation
```

The deep dive lives in [docs/architecture.md](docs/architecture.md); the core
vocabulary (entities, dependency closure, φ, "worthy" commits) is in
[docs/concepts.md](docs/concepts.md).

---

## 🖼️ Run gallery

**[See the gallery → `dataset/INDEX.md`](dataset/INDEX.md)** — a
**representative showcase**: runs where the bi-level search *worked through its
budget* (**20+ search steps**) and **climbed the documentation toward peak**,
each with the full auditable trace (search tree, per-node docs/code/φ, and the
generated test suite).

Documentation the search rewrote, step by step, until the agent could regenerate
the code correctly:

| Repo | Target | φ before → after | Steps |
|---|---|--:|--:|
| funcy | `funcy/seqs.py` | 0.000 → **0.870** | 20 |
| osmnx | `osmnx/utils_geo.py` | 0.400 → **0.850** | 20 |
| inflection | `inflection/__init__.py` | 0.692 → **0.885** | 23 |
| arrow | `arrow/util.py` | 0.875 → **0.958** | 20 |

…and more in the [full gallery](dataset/INDEX.md).

We deliberately publish **representative runs only** — sustained searches that
climb — rather than every run. Quick one-step wins, targets already at φ≈1.0
(nothing to improve), and still-hard cases (test-quality artifacts / not yet
doc-fixable) are excluded.

> Java is a single repo (jsoup) because the dependency-closure builder only
> supports single-module Maven so far — multi-module Maven projects aren't
> compatible yet, so their test classpath can't be built ([details](docs/languages.md#why-the-java-benchmark-is-a-single-repo)).

---

## 🗂️ Repository layout

```
src/docsearch/
├── main.py            # repo-level CLI entry point
├── agent/             # generic ReAct director loop + filesystem tools
├── llm/               # unified clients (OpenAI / Anthropic / Gemini) + tool-use + agent adapter
├── docgen/            # AST parsers (Python ast · Java tree-sitter) + batched per-entity doc generation
├── testgen/
│   └── react/         # ReAct, coverage-gated test author + per-language analyzers
├── search/            # bi-level search: closure, module builder, outer/inner, worthy, loop, evaluator
├── pipeline/          # entities, call graph, topo sort, code generator, evaluator contracts
├── prompts/           # prompt templates
├── utils/             # metrics (solve_rate / pass_rate / token ledger)
├── test_executor.py   # pytest runner + per-entity attribution
└── java_test_executor.py  # JUnit runner (javac + console launcher)
```

The full module-by-module tour is in [docs/architecture.md](docs/architecture.md).

---

## 📚 Documentation

| Page | What's inside |
|---|---|
| [Overview](docs/index.md) | What DocSearch is and the mental model |
| [Getting Started](docs/getting-started.md) | Install, API keys, your first run, reading the output |
| [Concepts](docs/concepts.md) | Entities · dependency closure · φ signal · worthy commits |
| [Architecture](docs/architecture.md) | The pipeline and the bi-level search, stage by stage |
| [CLI Reference](docs/cli.md) | Every flag, with examples |
| [Language Support](docs/languages.md) | Python and Java specifics |
| [News](#-news) | Release notes and feature write-ups |

A standalone documentation website is in the works; the `docs/` tree is written
as portable Markdown (with a starter [`mkdocs.yml`](mkdocs.yml)) so it can be
published with MkDocs Material, Docusaurus, or any static-site generator.

---

## 📝 Citation

DocSearch is the system behind our ICML 2026 paper. If you use it, please cite:

```bibtex
@inproceedings{cheng2026docsearch,
  title     = {Escaping Whack-a-Mole: Optimizing Documentation as Repo-Specific Playbooks for Coding Agents},
  author    = {Cheng, Yutong and Chen, Haifeng and Yu, Wenchao and Zhao, Xujiang and Gao, Peng and Cheng, Wei},
  booktitle = {Proceedings of the 43rd International Conference on Machine Learning (ICML)},
  year      = {2026}
}
```

## 📬 Contact

Questions, bug reports, and collaboration inquiries are welcome. Please
[open an issue](https://github.com/ccsnow127/docsearch/issues) for anything
actionable, or reach out to **Yutong Cheng** at
[yutongcheng@vt.edu](mailto:yutongcheng@vt.edu).

## 📄 License

Released under the MIT License (see `pyproject.toml`). A `LICENSE` file will
accompany the public release — if you have specific licensing needs for a
commercial deployment, please confirm the terms before redistributing.
