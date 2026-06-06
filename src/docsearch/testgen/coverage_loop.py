"""Coverage-driven test generation loop.

Iteratively prompts the LLM for new tests, validates each against the
reference, and stops when:

* branch coverage on the target entity reaches ``coverage_threshold``
  (default 90%); or
* the per-round coverage gain stays below ``min_gain`` for ``patience``
  consecutive rounds (default 0.01 / 2).

Coverage is measured via ``coverage.py`` over a single test pass.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from docsearch.llm.base import LLMClient
from docsearch.pipeline.entities import Entity, Module
from docsearch.prompts import render
from docsearch.testgen.extract import extract_tests
from docsearch.testgen.external_deps import detect_external_deps
from docsearch.testgen.filters import deduplicate, filter_direct
from docsearch.testgen.validator import validate_tests_against_reference


@dataclass
class TestGenConfig:
    __test__ = False  # don't let pytest collect this dataclass as a test class
    coverage_threshold: float = 0.9
    min_gain: float = 0.01
    patience: int = 2
    max_iterations: int = 10
    temperature: float = 0.7
    timeout: float = 30.0


@dataclass
class TestGenResult:
    __test__ = False
    entity: str
    tests: list[str] = field(default_factory=list)
    coverage: float = 0.0
    iterations: int = 0
    uncovered_lines: list[tuple[int, str]] = field(default_factory=list)


def generate_tests_for_entity(
    entity: Entity,
    module: Module,
    llm: LLMClient,
    *,
    config: TestGenConfig | None = None,
) -> TestGenResult:
    """Coverage-driven generate-validate loop for one entity."""
    cfg = config or TestGenConfig()
    external = detect_external_deps(entity.source)
    dep_signatures = _render_dep_signatures(module, entity)

    accumulated: list[str] = []
    last_coverage = 0.0
    no_progress = 0
    uncovered: list[tuple[int, str]] = []
    iteration = 0

    for iteration in range(1, cfg.max_iterations + 1):
        prompt = render(
            "test_generation",
            entity_name=entity.qualname,
            entity_type=entity.kind.value,
            signature=entity.signature,
            source_code=entity.source,
            dependency_signatures=dep_signatures or "(no internal callees)",
            uncovered_lines=_format_uncovered(uncovered),
            external_deps=external.as_human_readable(),
        )
        resp = llm.complete(prompt, temperature=cfg.temperature)

        try:
            preamble, candidates = extract_tests(resp.text)
        except ValueError:
            # Malformed output — skip this round but count it
            no_progress += 1
            if no_progress >= cfg.patience:
                break
            continue

        validated = validate_tests_against_reference(
            entity.source,
            candidates,
            preamble=preamble,
            timeout=cfg.timeout,
        )
        # The reference for *the entity* may not be importable standalone
        # (it might depend on other module entities). Fall back to the
        # whole module if the entity-only validation rejects everything.
        if not validated and candidates:
            validated = validate_tests_against_reference(
                _reference_module_source(module),
                candidates,
                preamble=preamble,
                timeout=cfg.timeout,
            )

        validated = filter_direct(validated, entity.qualname)
        merged = deduplicate(accumulated + validated)
        new_count = len(merged) - len(accumulated)
        accumulated = merged

        coverage, uncovered = _measure_coverage(
            entity, module, accumulated, preamble=preamble, timeout=cfg.timeout
        )
        gain = coverage - last_coverage
        last_coverage = coverage

        if coverage >= cfg.coverage_threshold:
            break
        if gain < cfg.min_gain:
            no_progress += 1
            if no_progress >= cfg.patience:
                break
        else:
            no_progress = 0

        if new_count == 0:
            # The LLM gave us nothing new this round
            no_progress += 1
            if no_progress >= cfg.patience:
                break

    return TestGenResult(
        entity=entity.qualname,
        tests=accumulated,
        coverage=last_coverage,
        iterations=iteration,
        uncovered_lines=uncovered,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render_dep_signatures(module: Module, entity: Entity) -> str:
    sigs: list[str] = []
    for callee in sorted(module.callees_of(entity.qualname)):
        e = module.entities.get(callee)
        if e is not None and e.signature:
            sigs.append(f"- {e.signature}")
    return "\n".join(sigs)


def _reference_module_source(module: Module) -> str:
    """Return the full reference source for whole-module validation.

    Prefer ``module.source`` (the original file, including module-level
    constants / imports / aliases) when available; fall back to
    stitching entity sources for ``Module`` instances built without one.
    """
    if module.source:
        return module.source
    parts: list[str] = []
    for e in module.entities.values():
        if e.source:
            parts.append(e.source)
    return "\n\n".join(parts)


def _format_uncovered(uncovered: list[tuple[int, str]]) -> str:
    if not uncovered:
        return "(none — first round or full coverage already reached)"
    return "\n".join(f"  line {n}: {src.strip()}" for n, src in uncovered[:20])


def _measure_coverage(
    entity: Entity,
    module: Module,
    tests: list[str],
    *,
    preamble: str,
    timeout: float,
) -> tuple[float, list[tuple[int, str]]]:
    """Return ``(branch_coverage, uncovered_lines)`` for ``entity``."""
    if not tests:
        return 0.0, []
    with tempfile.TemporaryDirectory(prefix="docsearch_cov_") as tmp:
        workdir = Path(tmp)
        ref_source = _reference_module_source(module)
        (workdir / "_reference.py").write_text(ref_source)

        test_path = workdir / "test_all.py"
        parts = [
            "import sys, os",
            "sys.path.insert(0, os.path.dirname(__file__))",
            "from _reference import *  # noqa: F401,F403",
            "",
        ]
        if preamble.strip():
            parts.append(preamble.rstrip())
            parts.append("")
        parts.append("\n\n".join(tests))
        parts.append("")
        body = "\n".join(parts)
        test_path.write_text(body)

        rc_path = workdir / ".coveragerc"
        rc_path.write_text(
            "[run]\nbranch = True\nsource = _reference\n"
        )

        cmd = [
            sys.executable,
            "-m",
            "coverage",
            "run",
            f"--rcfile={rc_path}",
            "-m",
            "pytest",
            "--tb=no",
            "-q",
            "-p",
            "no:cacheprovider",
            str(test_path),
        ]
        try:
            subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except subprocess.TimeoutExpired:
            return 0.0, []

        return _read_coverage(workdir, entity, ref_source)


def _read_coverage(
    workdir: Path, entity: Entity, ref_source: str
) -> tuple[float, list[tuple[int, str]]]:
    """Parse ``coverage.py``'s data file for branch coverage on ``entity``.

    We restrict the analysis to the line range of ``entity`` so partial
    module coverage doesn't dilute the metric.
    """
    try:
        import coverage  # type: ignore
    except ImportError:  # pragma: no cover
        return 0.0, []

    cov = coverage.Coverage(data_file=str(workdir / ".coverage"))
    cov.load()

    ref_path = str(workdir / "_reference.py")
    analysis = cov.analysis2(ref_path)
    # analysis2 returns (filename, executable, excluded, missing, missing_formatted)
    _, executable, _, missing, _ = analysis

    entity_lines = _entity_lines(entity, ref_source)
    if not entity_lines:
        return 0.0, []

    exec_in_entity = [n for n in executable if n in entity_lines]
    missing_in_entity = [n for n in missing if n in entity_lines]
    if not exec_in_entity:
        return 1.0, []

    line_cov = 1.0 - (len(missing_in_entity) / len(exec_in_entity))

    src_lines = ref_source.splitlines()
    uncovered = [
        (n, src_lines[n - 1] if n - 1 < len(src_lines) else "")
        for n in missing_in_entity
    ]
    return line_cov, uncovered


def _entity_lines(entity: Entity, ref_source: str) -> set[int]:
    """Best-effort: lines of ``ref_source`` that belong to ``entity``.

    We locate the entity's source as a substring and translate to line
    numbers. For methods, the substring may appear inside the class body
    — that's still correct.
    """
    if not entity.source:
        return set()
    idx = ref_source.find(entity.source.split("\n", 1)[0])
    if idx == -1:
        return set()
    start_line = ref_source.count("\n", 0, idx) + 1
    span = entity.source.count("\n") + 1
    return set(range(start_line, start_line + span))
