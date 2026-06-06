"""Generate tests for every entity in a module, with on-disk caching.

Cache format::

    {
      "config": {"coverage_threshold": 0.9, ...},
      "model": "gpt-4o",
      "entities": {
        "<qualname>": {
          "tests": ["def test_x(): ...", ...],
          "coverage": 0.93,
          "iterations": 3
        },
        ...
      }
    }
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from docsearch.llm.base import LLMClient
from docsearch.pipeline.entities import Module
from docsearch.testgen.coverage_loop import (
    TestGenConfig,
    TestGenResult,
    generate_tests_for_entity,
)


@dataclass
class ModuleTestGenResult:
    """Aggregate result for a whole module."""

    __test__ = False
    tests_by_entity: dict[str, list[str]] = field(default_factory=dict)
    per_entity: dict[str, TestGenResult] = field(default_factory=dict)
    total_tests: int = 0
    elapsed_seconds: float = 0.0
    from_cache: bool = False


def generate_module_tests(
    module: Module,
    llm: LLMClient,
    *,
    config: TestGenConfig | None = None,
    cache_path: Path | str | None = None,
    use_cache: bool = True,
) -> ModuleTestGenResult:
    """Run testgen for every entity in ``module``.

    If ``cache_path`` is set and points at an existing file, the cached
    tests are returned without invoking the LLM. Set ``use_cache=False``
    to force regeneration.
    """
    cfg = config or TestGenConfig()
    cache_file = Path(cache_path) if cache_path else None

    if use_cache and cache_file and cache_file.is_file():
        return _load_cache(cache_file, module)

    started = time.monotonic()
    tests_by_entity: dict[str, list[str]] = {}
    per_entity: dict[str, TestGenResult] = {}
    for qn in module.entities:
        entity = module.entities[qn]
        result = generate_tests_for_entity(entity, module, llm, config=cfg)
        per_entity[qn] = result
        tests_by_entity[qn] = result.tests

    total_tests = sum(len(t) for t in tests_by_entity.values())
    elapsed = time.monotonic() - started

    out = ModuleTestGenResult(
        tests_by_entity=tests_by_entity,
        per_entity=per_entity,
        total_tests=total_tests,
        elapsed_seconds=elapsed,
        from_cache=False,
    )

    if cache_file is not None:
        _write_cache(cache_file, out, cfg, llm)

    return out


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------

def _load_cache(path: Path, module: Module) -> ModuleTestGenResult:
    raw = json.loads(path.read_text())
    entities = raw.get("entities", {})
    tests_by_entity: dict[str, list[str]] = {}
    per_entity: dict[str, TestGenResult] = {}
    for qn in module.entities:
        block = entities.get(qn) or {}
        tests = list(block.get("tests", []))
        tests_by_entity[qn] = tests
        per_entity[qn] = TestGenResult(
            entity=qn,
            tests=tests,
            coverage=block.get("coverage", 0.0),
            iterations=block.get("iterations", 0),
            uncovered_lines=[],
        )
    return ModuleTestGenResult(
        tests_by_entity=tests_by_entity,
        per_entity=per_entity,
        total_tests=sum(len(t) for t in tests_by_entity.values()),
        elapsed_seconds=0.0,
        from_cache=True,
    )


def _write_cache(
    path: Path,
    result: ModuleTestGenResult,
    config: TestGenConfig,
    llm: LLMClient,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": getattr(llm, "model", "unknown"),
        "config": asdict(config),
        "entities": {
            qn: {
                "tests": r.tests,
                "coverage": r.coverage,
                "iterations": r.iterations,
            }
            for qn, r in result.per_entity.items()
        },
    }
    path.write_text(json.dumps(payload, indent=2))
