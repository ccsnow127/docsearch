"""Run generated code against a test suite and collect per-entity pass rates.

Inputs:

* ``code``: the generated module source (single file containing every
  entity, since cross-entity calls must resolve at runtime);
* ``tests_by_entity``: ``{entity_qualname: [test_function_source, ...]}``.

For each entity a temporary layout is written::

    /tmp/<run>/
        module_under_test.py    # generated code
        test_<entity>.py        # tests targeting that entity

then pytest is invoked as a subprocess (test pollution / hangs stay
isolated) and verbose output is parsed, attributing each pass/fail to
the owning entity by filename.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EntityResult:
    """Per-entity outcome of one evaluation pass."""

    qualname: str
    passed: int = 0
    failed: int = 0
    errors: int = 0
    failures: list[str] = field(default_factory=list)  # error/failure messages

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors

    @property
    def phi(self) -> float:
        if self.total == 0:
            return 0.0
        return self.passed / self.total


@dataclass
class EvaluationResult:
    """Result of evaluating one (code, tests) pair across all entities."""

    per_entity: dict[str, EntityResult] = field(default_factory=dict)
    setup_error: str | None = None  # syntax error / import failure / pytest crash

    def phi(self, entity: str) -> float:
        return self.per_entity.get(entity, EntityResult(entity)).phi

    def to_phi_dict(self) -> dict[str, float]:
        return {q: r.phi for q, r in self.per_entity.items()}


# ---------------------------------------------------------------------------

def evaluate(
    code: str,
    tests_by_entity: dict[str, list[str]],
    *,
    module_filename: str = "module_under_test.py",
    timeout: float = 60.0,
    workdir: Path | None = None,
    data_dir: Path | None = None,
) -> EvaluationResult:
    """Run the full test suite against ``code``.

    Each entity's tests are written to its own file so per-entity stats
    are unambiguous. We launch one pytest subprocess for the whole
    bundle (much faster than per-entity) and parse its stdout.

    ``data_dir`` is an optional directory whose contents are copied into
    the workdir before tests run; this is how benchmarks like ``hone``
    or ``lice`` ship test fixtures (CSVs, templates, ...) that the
    reference / generated code expects to find relative to the cwd.

    ``setup_error`` is populated if the generated code is unparseable,
    the import itself fails, or pytest crashes before running any tests.
    """
    if workdir is None:
        tmpdir_obj = tempfile.TemporaryDirectory(prefix="docsearch_eval_")
        workdir_path = Path(tmpdir_obj.name)
        cleanup = tmpdir_obj.cleanup
    else:
        workdir_path = Path(workdir)
        workdir_path.mkdir(parents=True, exist_ok=True)
        cleanup = lambda: None  # noqa: E731

    try:
        return _evaluate_in(
            workdir_path, code, tests_by_entity, module_filename, timeout, data_dir
        )
    finally:
        cleanup()


def _evaluate_in(
    workdir: Path,
    code: str,
    tests_by_entity: dict[str, list[str]],
    module_filename: str,
    timeout: float,
    data_dir: Path | None,
) -> EvaluationResult:
    if data_dir is not None and data_dir.is_dir():
        import shutil
        for item in data_dir.iterdir():
            dest = workdir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

    module_path = workdir / module_filename
    module_path.write_text(code)

    module_stem = module_path.stem

    # Quick syntax check first so the search loop can detect "broken
    # generation" without paying for a pytest subprocess.
    try:
        compile(code, module_filename, "exec")
    except SyntaxError as e:
        result = EvaluationResult(setup_error=f"SyntaxError in generated code: {e}")
        for entity, tests in tests_by_entity.items():
            r = EntityResult(qualname=entity)
            for _ in tests:
                r.errors += 1
                r.failures.append(f"setup error: {e}")
            result.per_entity[entity] = r
        return result

    # Write one test file per entity. Each file imports * from the module.
    entity_to_filename: dict[str, str] = {}
    for entity, tests in tests_by_entity.items():
        fname = _entity_to_filename(entity)
        entity_to_filename[entity] = fname
        (workdir / fname).write_text(_render_test_file(module_stem, tests))

    # Run pytest in verbose mode so each test produces a line like
    # ``test_double.py::test_basic PASSED`` (per-file attribution).
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--tb=line",
        "-v",
        "--no-header",
        "-p",
        "no:cacheprovider",
        str(workdir),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired as e:
        result = EvaluationResult(setup_error=f"pytest timed out after {timeout}s: {e}")
        for entity, tests in tests_by_entity.items():
            r = EntityResult(qualname=entity)
            r.errors += len(tests)
            r.failures.append("timeout during evaluation")
            result.per_entity[entity] = r
        return result

    return _parse_stdout(proc.stdout, proc.stderr, tests_by_entity, entity_to_filename)


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9]+")


def _entity_to_filename(entity_qualname: str) -> str:
    slug = _FILENAME_SAFE.sub("_", entity_qualname).strip("_") or "entity"
    return f"test_{slug}.py"


def _render_test_file(module_stem: str, tests: list[str]) -> str:
    # `import pytest` is unconditionally injected because tests often use
    # `pytest.raises` etc. without re-stating the import (the loader's
    # `_split_test_functions` drops module-level imports). pytest is a
    # hard dependency of this package so the import is always available.
    #
    # `from <mod> import *` skips single-underscore names by Python
    # convention; we explicitly re-bind those into the test globals so
    # tests for private helpers (e.g. ``_mul``) can find them.
    header = textwrap.dedent(
        f"""\
        import sys, os
        import pytest  # noqa: F401
        sys.path.insert(0, os.path.dirname(__file__))
        from {module_stem} import *  # noqa: F401,F403
        import {module_stem} as _mut
        for _name in dir(_mut):
            if _name.startswith('_') and not _name.startswith('__'):
                globals()[_name] = getattr(_mut, _name)
        del _mut, _name
        """
    )
    body = "\n\n".join(tests)
    return header + "\n" + body + "\n"


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------

# pytest -v emits one line per test:
#   test_double.py::test_basic PASSED   [ 50%]
#   tests/sub/test_x.py::test_y FAILED  [100%]
# We also accept ERROR (e.g., collection / fixture errors).
_VERBOSE_RESULT = re.compile(
    r"^(?P<file>\S+\.py)::(?P<test>[^\s]+)\s+(?P<status>PASSED|FAILED|ERROR)\b",
    re.MULTILINE,
)

# Summary section after FAILURES gives the assertion message:
#   FAILED test_double.py::test_basic - assert 6 == 7
_SUMMARY_LINE = re.compile(
    r"^(?P<status>FAILED|ERROR)\s+(?P<file>\S+\.py)::(?P<test>[^\s]+)(?:\s+-\s+(?P<msg>.+))?$",
    re.MULTILINE,
)


def _parse_stdout(
    stdout: str,
    stderr: str,
    tests_by_entity: dict[str, list[str]],
    entity_to_filename: dict[str, str],
) -> EvaluationResult:
    file_to_entity = {v: k for k, v in entity_to_filename.items()}
    result = EvaluationResult()
    for entity in tests_by_entity:
        result.per_entity[entity] = EntityResult(qualname=entity)

    # 1) Per-test outcome lines (counts).
    seen: set[tuple[str, str]] = set()  # dedupe (file, test) pairs
    for m in _VERBOSE_RESULT.finditer(stdout):
        file_name = Path(m.group("file")).name
        entity = file_to_entity.get(file_name)
        if entity is None:
            continue
        key = (file_name, m.group("test"))
        if key in seen:
            continue
        seen.add(key)
        r = result.per_entity[entity]
        status = m.group("status")
        if status == "PASSED":
            r.passed += 1
        elif status == "FAILED":
            r.failed += 1
        else:
            r.errors += 1

    # 2) Summary lines (assertion / error messages).
    for m in _SUMMARY_LINE.finditer(stdout):
        file_name = Path(m.group("file")).name
        entity = file_to_entity.get(file_name)
        if entity is None:
            continue
        msg = (m.group("msg") or "").strip()
        if msg:
            result.per_entity[entity].failures.append(msg)

    # 3) If pytest produced no per-test lines but did emit stderr or an
    # ERROR-ish stdout (e.g., import-time failure), surface it.
    has_any_result = any(r.total > 0 for r in result.per_entity.values())
    if not has_any_result and (stderr.strip() or "error" in stdout.lower()):
        result.setup_error = (stderr.strip() or stdout.strip())[-2000:]

    return result
