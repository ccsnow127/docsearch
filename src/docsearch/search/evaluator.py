"""Evaluators behind the :class:`contracts.Evaluator` protocol.

Two evaluators are provided, one per supported language. Both take generated
source for the module under test, run the *hidden* balanced test suite through
the project's existing executors, and map the raw results to a per-entity
:class:`contracts.EvaluationResult`.

The generated code never sees these tests: the executors load the code into a
fresh build (Maven/javac classpath for Java, a patched module import for
Python), run the suite, and return pass/fail counts plus per-test outcome
lines. We attribute every test outcome to its owning entity by reusing the
executor's own ``_test_name_to_entity`` mapping, so per-entity phi reflects the
real pass rate rather than a binary solved flag.

Java is the primary path and goes through :class:`JavaTestExecutor`
(Maven/JUnit, never reimplemented here). Python goes through
:class:`TestExecutor` (pytest). On a compile/setup failure the executor reports
no per-test outcomes; in that case :attr:`EvaluationResult.setup_error` is set
and the TESTED entities (those the suite attributes >=1 test to) are marked
errored. Entities with no tests are never seeded into the result -- they carry
no phi signal, so forcing them to phi=0 would only dilute the mean phi (which
is taken over tested entities) and waste search effort refining them.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from docsearch.search.contracts import EntityResult, EvaluationResult

# ANSI colour codes leak into JUnit console output; strip them before parsing.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# Java JUnit verbose lines:
#   "    methodName = 'test_Renko_getOhlcData_single_row'"  then later
#   "    status: ✔ SUCCESSFUL" / "status: ✘ FAILED" / "status: ⛔ ABORTED"
_JAVA_METHOD = re.compile(r"methodName\s*=\s*'(test_?\w+)'")
_JAVA_STATUS = re.compile(r"status:\s*\S?\s*(SUCCESSFUL|FAILED|ABORTED)")

# Python pytest -v lines:
#   "test_file.py::test_name PASSED   [ 50%]"
_PY_RESULT = re.compile(
    r"::(?P<test>test_?\w+)\s+(?P<status>PASSED|FAILED|ERROR)\b"
)


# Test method/function names in either JUnit ("void test_foo()") or pytest
# ("def test_foo("); we only need the bare ``test_*`` token to attribute it.
_TEST_NAME = re.compile(r"\btest_?\w+\b")


def _tested_entities(test_executor) -> list[str]:
    """Entities the suite actually exercises (>=1 test attributed to them).

    Read straight from the test file via the executor's own
    ``_test_name_to_entity`` so we never seed phi for an untested entity. An
    entity with no tests has no phi signal: forcing it to phi=0 would dilute
    the mean and waste refinement effort, so it must be absent entirely.
    """
    try:
        content = Path(test_executor.test_suite_path).read_text()
    except OSError:
        return []
    entities: list[str] = []
    seen: set[str] = set()
    for m in _TEST_NAME.finditer(content):
        entity = test_executor._test_name_to_entity(m.group(0))
        if entity and entity not in seen:
            seen.add(entity)
            entities.append(entity)
    return entities


def _entities_errored(entities: list[str], message: str) -> EvaluationResult:
    """Build a result where every TESTED entity is errored by a setup failure.

    Only entities with at least one test get an explicit errored (phi=0)
    result; untested entities stay absent so they never enter the phi mean.
    """
    result = EvaluationResult(setup_error=message)
    for entity in entities:
        r = EntityResult(qualname=entity)
        r.errors = 1
        r.failures.append(message)
        result.per_entity[entity] = r
    return result


class JavaEvaluator:
    """:class:`contracts.Evaluator` for Java, backed by :class:`JavaTestExecutor`.

    Given generated Java source it runs the existing balanced JUnit test file
    through the executor (which compiles with javac and runs the JUnit console
    launcher), then attributes each test outcome to its entity via the
    executor's ``_test_name_to_entity``.
    """

    def __init__(
        self,
        test_executor,
        target_module: str,
        repo_path: str,
        source_class_name: str = "",
        entities: Optional[list[str]] = None,
        dependency_classpath: str = "",
        target_package: str = "",
    ):
        """
        Args:
            test_executor: A configured :class:`JavaTestExecutor`. Its
                ``test_suite_path`` already points at the balanced test file.
            target_module: Name of the module under test (e.g. "Indicators").
            repo_path: Path to the repository root.
            source_class_name: Name of the public class the generated code
                defines; used to ensure the written file matches its class.
            entities: Optional fixed entity universe, kept for API
                compatibility. It does NOT force untested entities into the
                result: only entities the suite actually tests are reported,
                so the mean phi stays over tested entities.
            dependency_classpath: The repo closure ``deps_classpath`` to wire
                into the executor so the generated target compiles/runs against
                the ground-truth dependency closure. Empty preserves today's
                self-contained behavior.
            target_package: Java package of the target file (e.g.
                "org.jsoup.select"); threaded into the executor so generated and
                test sources land under their package directory. Empty means the
                default (unnamed) package.
        """
        self.test_executor = test_executor
        self.target_module = target_module
        self.repo_path = Path(repo_path).resolve()
        self.source_class_name = source_class_name
        self.entities = list(entities) if entities else []
        self.dependency_classpath = dependency_classpath
        self.target_package = target_package

        # Thread the closure into the executor when the caller supplied it,
        # without clobbering an executor that was already configured directly.
        if dependency_classpath and not getattr(test_executor, "dependency_classpath", ""):
            test_executor.dependency_classpath = dependency_classpath
        if target_package and not getattr(test_executor, "target_package", ""):
            test_executor.target_package = target_package

    def evaluate(self, code: str) -> EvaluationResult:
        run_result = self.test_executor.run(code)

        # Compile / setup failure: the executor produced no runnable tests.
        if run_result.compile_error or run_result.runtime_error:
            message = run_result.compile_error or run_result.runtime_error or ""
            detail = "; ".join(run_result.errors[:5]) if run_result.errors else ""
            full = f"{message} | {detail}".strip(" |") or "Java setup error"
            return _entities_errored(_tested_entities(self.test_executor), full)

        return self._attribute(run_result)

    def _attribute(self, run_result) -> EvaluationResult:
        """Map JUnit verbose output to per-entity pass/fail counts.

        Only entities that actually have tests appear in the result. We never
        seed the module's entity universe to phi=0, since untested entities
        carry no signal and would otherwise dilute the reported mean phi.
        """
        result = EvaluationResult()

        clean = _ANSI.sub("", run_result.output or "")
        lines = clean.split("\n")

        # Walk the verbose tree: each test's methodName precedes its status.
        current_test: Optional[str] = None
        seen: set[str] = set()
        any_outcome = False
        for line in lines:
            m = _JAVA_METHOD.search(line)
            if m:
                current_test = m.group(1)
                continue
            if current_test is None:
                continue
            sm = _JAVA_STATUS.search(line)
            if not sm:
                continue
            if current_test not in seen:
                seen.add(current_test)
                any_outcome = True
                self._record(result, current_test, sm.group(1))
            current_test = None

        # If the verbose lines were unavailable, fall back to the summary
        # counts the executor already parsed so phi is at least globally right.
        if not any_outcome and run_result.total > 0:
            return self._attribute_from_summary(run_result)

        if not any_outcome:
            message = "; ".join(run_result.errors[:5]) or "no Java tests ran"
            return _entities_errored(_tested_entities(self.test_executor), message)

        self._attach_failure_messages(result, run_result.errors)
        return result

    def _record(self, result: EvaluationResult, test_name: str, status: str) -> None:
        entity = self.test_executor._test_name_to_entity(test_name)
        r = result.per_entity.get(entity)
        if r is None:
            r = EntityResult(qualname=entity or test_name)
            result.per_entity[r.qualname] = r
        if status == "SUCCESSFUL":
            r.passed += 1
        elif status == "FAILED":
            r.failed += 1
        else:  # ABORTED / skipped count as errors
            r.errors += 1

    def _attribute_from_summary(self, run_result) -> EvaluationResult:
        """No per-test lines: spread the summary counts using failure targets.

        Failures carry a ``Target: Entity`` tag from the executor; remaining
        passes are credited to entities with no recorded failure. We work over
        the entities the suite actually tests, not the module universe, so
        untested entities never get a (diluting) phi=0 row.
        """
        result = EvaluationResult()
        tested = _tested_entities(self.test_executor)
        for entity in tested:
            result.per_entity[entity] = EntityResult(qualname=entity)
        for err in run_result.errors:
            m = re.search(r"Target:\s*([\w.]+)\s*\|", err)
            if not m:
                continue
            entity = m.group(1)
            r = result.per_entity.setdefault(entity, EntityResult(qualname=entity))
            r.failed += 1
            r.failures.append(err)
        failed = sum(r.failed for r in result.per_entity.values())
        passes = max(run_result.passed, run_result.total - failed)
        clean_entities = [e for e in tested if result.per_entity[e].failed == 0]
        if clean_entities and passes > 0:
            base, extra = divmod(passes, len(clean_entities))
            for i, entity in enumerate(clean_entities):
                result.per_entity[entity].passed = base + (1 if i < extra else 0)
        return result

    def _attach_failure_messages(self, result: EvaluationResult, errors: list[str]) -> None:
        for err in errors:
            m = re.search(r"Target:\s*([\w.]+)\s*\|", err)
            if not m:
                continue
            r = result.per_entity.get(m.group(1))
            if r is not None:
                r.failures.append(err)


class PythonEvaluator:
    """:class:`contracts.Evaluator` for Python, backed by :class:`TestExecutor`.

    Mirrors :class:`JavaEvaluator`: it runs generated code through the pytest
    executor and attributes per-test PASSED/FAILED/ERROR lines to entities via
    the executor's ``_test_name_to_entity``. It produces the same per-entity
    shape as :class:`JavaEvaluator`, but the run itself goes through the project's
    :class:`TestExecutor` rather than a private pytest invocation.
    """

    def __init__(
        self,
        test_executor,
        target_module: str,
        repo_path: str,
        entities: Optional[list[str]] = None,
    ):
        """
        Args:
            test_executor: A configured :class:`TestExecutor` whose
                ``test_suite_path`` points at the balanced test file.
            target_module: Importable module path being patched (e.g.
                "stocktrends.indicators").
            repo_path: Path to the repository root.
            entities: Optional fixed entity universe (see JavaEvaluator).
        """
        self.test_executor = test_executor
        self.target_module = target_module
        self.repo_path = Path(repo_path).resolve()
        self.entities = list(entities) if entities else []

    def evaluate(self, code: str) -> EvaluationResult:
        # Syntax check up front so a broken generation is a clean setup error
        # without paying for a pytest subprocess.
        try:
            compile(code, "<generated>", "exec")
        except SyntaxError as e:
            return _entities_errored(
                _tested_entities(self.test_executor),
                f"SyntaxError in generated code: {e}",
            )

        run_result = self.test_executor.run(code)
        return self._attribute(run_result)

    def _resolve_entity(self, test_name: str):
        """Map a test name to a REAL entity by longest-prefix match against the
        known entity universe -- robust to descriptive names the numeric-suffix
        heuristic mis-parses. Returns ``None`` when the test cannot be tied to a
        real module entity (e.g. a module-level behavior test like
        ``test_database_module_skip_true_when_no_json``): seeding such a test as
        a junk 'entity' at phi=0 would pollute the mean phi and invent a fake
        'hardest entity' the search then cannot refine."""
        raw = test_name[5:] if test_name.startswith("test_") else test_name
        chosen, chosen_len = None, -1
        for e in self.entities:
            for form in {e, e.replace(".", "_"), e.split(".")[-1]}:
                if form and (raw == form or raw.startswith(form + "_")) and len(form) > chosen_len:
                    chosen, chosen_len = e, len(form)
        if chosen is not None:
            return chosen
        fallback = self.test_executor._test_name_to_entity(test_name)
        # When we know the entity universe, only accept a fallback that is a real
        # entity; otherwise the test is unattributable -> drop it from phi.
        if self.entities and fallback not in self.entities:
            return None
        return fallback

    def _tested_entities(self):
        try:
            content = Path(self.test_executor.test_suite_path).read_text()
        except OSError:
            return []
        out, seen = [], set()
        for m in _TEST_NAME.finditer(content):
            e = self._resolve_entity(m.group(0))
            if e and e not in seen:
                seen.add(e); out.append(e)
        return out

    def _attribute(self, run_result) -> EvaluationResult:
        # Only entities with at least one test appear in the result; untested
        # entities carry no signal and must not be seeded to phi=0 (that would
        # dilute the mean phi and waste refinement effort on them).
        result = EvaluationResult()

        output = run_result.output or ""
        seen: set[str] = set()
        any_outcome = False
        for m in _PY_RESULT.finditer(output):
            test_name = m.group("test")
            if test_name in seen:
                continue
            seen.add(test_name)
            any_outcome = True
            entity = self._resolve_entity(test_name)
            if entity is None:
                continue  # unattributable test (e.g. module-level) — keep it out of phi
            r = result.per_entity.get(entity)
            if r is None:
                r = EntityResult(qualname=entity)
                result.per_entity[r.qualname] = r
            status = m.group("status")
            if status == "PASSED":
                r.passed += 1
            elif status == "FAILED":
                r.failed += 1
            else:
                r.errors += 1

        # No per-test lines: import/collection failure -> setup error.
        if not any_outcome:
            message = "; ".join(run_result.errors[:5]) or (output[-2000:] if output.strip() else "no Python tests ran")
            return _entities_errored(self._tested_entities(), message)

        self._attach_failure_messages(result, run_result.errors)
        return result

    def _attach_failure_messages(self, result: EvaluationResult, errors: list[str]) -> None:
        for err in errors:
            m = re.search(r"Target:\s*([\w.]+)\s*\|", err)
            if not m:
                continue
            target = m.group(1)
            r = result.per_entity.get(target)
            if r is None:
                # The ``Target:`` name was produced by the executor's raw
                # ``_test_name_to_entity`` heuristic, which mis-parses
                # descriptive / doubled test names (e.g.
                # ``normalize_timestamp_normalize_timestamp_microseconds_...``).
                # Re-resolve it to a real entity key — the SAME longest-prefix
                # match used to key ``per_entity`` — so the failure attaches.
                # Without this the diagnose step gets no error context and the
                # search can never improve a sub-1.0 entity.
                r = result.per_entity.get(self._resolve_entity("test_" + target))
            if r is not None:
                r.failures.append(err)
