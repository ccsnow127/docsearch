# DocSearch — Representative Run Gallery

A **representative showcase**: runs where the DocSearch bi-level search **worked through its budget — 20+ search steps — and climbed the documentation toward peak**, so the agent could regenerate more of the code correctly. Model `gpt-5.2-us`, `--budget 10 --width 2`. Each row links to the slim, fully auditable trace: the search tree, every node's docs/code/φ, and the generated test suite. (Verbose agent transcripts and bulky `repo_sources/` copies are omitted.)

**φ** = the per-entity pass-rate of code regenerated from the docs alone; the table shows bootstrap (initial) mean φ, the final mean φ after search, and **Steps** = search nodes explored (~budget × width).

## ▲ 7 representative runs — sustained search, climbing to peak

| Repo | Lang | Target file | Entities | Tests | Init φ | Final φ | Δ | Steps | Trace |
|---|---|---|--:|--:|--:|--:|--:|--:|---|
| **funcy** | 🐍 py | `funcy/seqs.py` | 23 | 24 | 0.000 | 0.870 | ▲ +0.870 | 20 | [trace](traces/funcy/) |
| **osmnx** | 🐍 py | `osmnx/utils_geo.py` | 8 | 22 | 0.400 | 0.850 | ▲ +0.450 | 20 | [trace](traces/osmnx/) |
| **inflection** | 🐍 py | `inflection/__init__.py` | 13 | 15 | 0.692 | 0.885 | ▲ +0.192 | 23 | [trace](traces/inflection/) |
| **arrow** | 🐍 py | `arrow/util.py` | 6 | 19 | 0.875 | 0.958 | ▲ +0.083 | 20 | [trace](traces/arrow/) |
| **jinja** | 🐍 py | `src/jinja2/utils.py` | 22 | 28 | 0.788 | 0.833 | ▲ +0.045 | 22 | [trace](traces/jinja/) |
| **python-slugify** | 🐍 py | `slugify/slugify.py` | 2 | 28 | 0.811 | 0.839 | ▲ +0.028 | 21 | [trace](traces/python-slugify/) |
| **scapy** | 🐍 py | `scapy/utils6.py` | 26 | 40 | 0.926 | 0.936 | ▲ +0.010 | 23 | [trace](traces/scapy/) |

> This gallery shows representative runs only (≥20 search steps with a real φ gain). For context, the broader experiment also produced quick climbs (improved in <20 steps), targets already at φ≈1.0 at bootstrap (nothing to improve), and harder cases still under investigation (test-quality artifacts or not yet doc-fixable) — these are not published here.
