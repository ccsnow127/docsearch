"""A test-suite generator driven by the generic ReAct runtime in ``agent/``.

This mirrors :class:`docsearch.search.codegen_agent.AgentCodeGenerator` — the
same ReAct-generator shape — but for the *opposite* role: instead of
implementing a module behind a hidden test suite, this agent *writes the test
suite* for a given source file. It runs the director loop
(:func:`agent.runtime.run_agent`) over a private workspace: the agent reads the
REAL source (for test generation the agent SHOULD see the module under test),
writes a test file, and iterates against a ``run_tests`` feedback tool until the
tests compile, ALL pass against the ground-truth source, and the
coverage / min-tests target is met.

Unlike the code-gen agent (where leaking the tests would destroy the search),
here the source is the agent's source of truth and the feedback tool runs the
suite against it. The feedback machinery is OUR :class:`LanguageAdapter`
(``run_tests`` + ``measure_coverage``), not the external ``hl`` package — the
report below mirrors the structure of ``agent.feedback_tools.format_probe`` but
is implemented entirely over our adapters.

The public entry point keeps the existing CLI/output-file contract intact:
``ReactTestGenerator(config).generate(source_file, output_file, language)``
returns a :class:`~test_generator.models.TestSuite`, writing the test file to
``output_file`` (or printing via the CLI) exactly as before.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from docsearch.agent.runtime import run_agent
from docsearch.agent.tools import Tool, default_tools

from .analyzer.base import LanguageAdapter
from .analyzer.java_adapter import JavaAdapter
from .analyzer.python_adapter import PythonAdapter
from .config import TestGeneratorConfig
from .llm.react_adapter import make_testgen_llm
from .models import Coverage, Language, TestResult, TestSuite

_FENCE_OPEN = re.compile(r"^\s*```(?:java|python|py)?\s*\n?", re.IGNORECASE)
_FENCE_CLOSE = re.compile(r"\n?```\s*$")

# Count test methods to enforce the min-tests floor (best-effort, per language).
_PY_TEST_DEF = re.compile(r"^\s*def\s+test\w*\s*\(", re.MULTILINE)
_JAVA_TEST_ANNOT = re.compile(r"@Test\b")


def _strip_code_fences(text: str) -> str:
    """Remove a single leading/trailing markdown fence if the agent left one."""
    if not text:
        return ""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _FENCE_OPEN.sub("", stripped, count=1)
        stripped = _FENCE_CLOSE.sub("", stripped)
    return stripped.strip()


# Failure markers in runner output — used when the adapter cannot parse a
# "N passed" summary (e.g. pytest reports only "1 failed", JUnit reports a
# compilation/build error). Keeps the all-passing contract honest.
_FAILURE_MARKERS = re.compile(
    r"\b\d+\s+failed\b|\berror\b|FAILED|COMPILATION ERROR|BUILD FAILURE|"
    r"cannot find symbol|Traceback|Failures:\s*[1-9]|Errors:\s*[1-9]",
    re.IGNORECASE,
)


def _output_has_failures(output: str) -> bool:
    """True if raw runner output shows failures/errors (or failed to compile)."""
    return bool(output) and bool(_FAILURE_MARKERS.search(output))


def _count_tests(language: str, content: str) -> int:
    """Best-effort count of test methods in a suite file."""
    if language == "java":
        return len(_JAVA_TEST_ANNOT.findall(content))
    return len(_PY_TEST_DEF.findall(content))


# --------------------------------------------------------------------------- #
# Workspace file naming — match analyzer/base.get_test_file_name
# --------------------------------------------------------------------------- #
def _test_filename(adapter: LanguageAdapter, source_path: Path) -> str:
    """test_<stem>.py / <Stem>Test.java, exactly as the adapter expects."""
    return adapter.get_test_file_name(source_path)


def _source_basename(source_path: Path) -> str:
    """The module-under-test filename the suite imports/compiles against."""
    return source_path.name


# Matches a Java ``package org.foo.bar;`` declaration.
_JAVA_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)


def _java_package(source_text: str) -> str:
    """The package declared by ``package ...;`` in Java source ("" if none)."""
    m = _JAVA_PACKAGE.search(source_text)
    return m.group(1) if m else ""


def _packaged_relpath(filename: str, package: str) -> str:
    """Workspace-relative path placing ``filename`` under its ``package`` dir.

    e.g. ``("CssParser.java", "org.jsoup.select")`` ->
    ``"org/jsoup/select/CssParser.java"``. Empty package returns the bare
    filename, preserving the default-package single-file layout.
    """
    if not package:
        return filename
    return os.path.join(*package.split("."), filename)


# --------------------------------------------------------------------------- #
# run_tests feedback tool (over OUR adapters — never hl)
# --------------------------------------------------------------------------- #
def _failing_block(result: TestResult) -> "list[str]":
    """Mirror feedback_tools.format_probe's failing block, over a TestResult.

    The adapter does not retain per-test tracebacks structurally, so we surface
    the captured ``failure_details`` plus the tail of the raw runner output,
    which contains the FULL traceback of each failing test.
    """
    if result.success and result.total > 0:
        return ["\n## All tests pass."]
    out = [
        f"\n## FAILING / ERRORING tests (failed={result.failed}, "
        f"errors={result.errors}) — READ the traceback and fix the exact error "
        "(wrong arg, wrong attribute, wrong import, bad assertion):"
    ]
    for detail in (result.failure_details or [])[:6]:
        name = detail.get("test") or detail.get("type") or "failure"
        reason = str(detail.get("reason") or detail.get("message") or "").strip()
        if len(reason) > 1400:
            reason = "...\n" + reason[-1400:]
        out.append(f"### {name}\n{reason}")
    # The runner output carries the full tracebacks; show the tail.
    raw = (result.output or "").strip()
    if raw:
        if len(raw) > 2400:
            raw = "...\n" + raw[-2400:]
        out.append("### runner output (full traceback)\n" + raw)
    return out


def _uncovered_block(coverage: Optional[Coverage]) -> "list[str]":
    if coverage is None:
        return []
    uncovered = coverage.uncovered_lines or []
    if not uncovered:
        return []
    shown = ", ".join(str(x) for x in uncovered[:40])
    return [
        "\n## Uncovered source lines (cover these to raise coverage): "
        + shown + (" ..." if len(uncovered) > 40 else "")
    ]


def _format_probe(language: str, suite_content: str,
                  coverage: Optional[Coverage], result: TestResult) -> str:
    """Cheap report (metrics + failing tracebacks + uncovered), our-adapter flavored."""
    total = result.total
    pass_rate = (result.passed / total) if total else 0.0
    line = coverage.line if coverage else 0.0
    branch = coverage.branch if coverage else 0.0
    size = _count_tests(language, suite_content)
    lines = [
        f"pass_rate={pass_rate:.3f}  line_coverage={line:.3f}  "
        f"branch_coverage={branch:.3f}  tests={size}  "
        f"(passed={result.passed} failed={result.failed} errors={result.errors})"
    ]
    lines += _failing_block(result)
    lines += _uncovered_block(coverage)
    return "\n".join(lines)


def _run_suite(adapter: LanguageAdapter, workspace: str, test_file: str,
               source_file: str, timeout: int) -> "tuple[Optional[Coverage], TestResult]":
    """Run the current suite against the ground-truth source via the adapter.

    Prefers ``measure_coverage`` (gives pass/fail AND coverage in one run); falls
    back to ``run_tests`` if coverage measurement is unavailable.
    """
    test_path = Path(workspace) / test_file
    source_path = Path(workspace) / source_file
    try:
        coverage, result = adapter.measure_coverage(test_path, source_path, timeout)
        return coverage, result
    except Exception:
        result = adapter.run_tests(test_path, source_path, timeout)
        return None, result


def _make_run_tests_tool(adapter: LanguageAdapter, language: str, test_file: str,
                         source_file: str, timeout: int,
                         validator=None, entities=None) -> Tool:
    """The single feedback Tool (a closure): read the suite, run it against the
    ground-truth source, return pass_rate / coverage / count + full tracebacks,
    plus any test-quality problems (mock usage, unattributable names, or tests
    that never call the real entity) the agent must fix."""

    def run(workspace: str, args: dict) -> str:
        full = os.path.join(workspace, test_file)
        if not os.path.isfile(full):
            return (f"(no {test_file} to run yet — write the test file first, "
                    f"importing/using the module under test)")
        content = open(full, encoding="utf-8", errors="replace").read()
        if not content.strip():
            return f"(no {test_file} to run yet — it is empty; write some tests first)"
        coverage, result = _run_suite(adapter, workspace, test_file, source_file, timeout)
        report = _format_probe(language, content, coverage, result)
        if validator is not None:
            issues = validator(content)
            if issues:
                report += (
                    "\n\n## Test-quality problems — the suite is NOT acceptable until "
                    "these are fixed:\n- " + "\n- ".join(issues[:8])
                    + (f"\n  ... and {len(issues) - 8} more" if len(issues) > 8 else "")
                    + "\nValid entities to target: " + _entity_examples(entities or []) + "."
                )
        return report

    return Tool(
        name="run_tests",
        description=(
            "Run the current test file against the GROUND-TRUTH source and get "
            "back pass_rate, line/branch coverage, the number of tests, the FULL "
            "traceback of every FAILING/ERRORING test, the uncovered source "
            "lines, and any tests whose NAME is not attributable to a real "
            "entity. This is your feedback channel: call it after every edit. "
            "FIX failing or mis-named tests (wrong assertion/API/name); only "
            "delete a test as a last resort. The FINAL suite must be all-passing "
            "AND every test name must map to a real class+method."),
        input_schema={"type": "object", "properties": {}},
        run=run,
        kind="feedback",
    )


# --------------------------------------------------------------------------- #
# done_check — the real termination contract
# --------------------------------------------------------------------------- #
def _make_done_check(adapter: LanguageAdapter, language: str, test_file: str,
                     source_file: str, config: TestGeneratorConfig,
                     validator=None, entities=None):
    """``done`` is accepted only when the suite is non-empty, compiles, ALL tests
    pass against the ground-truth source, EVERY test really exercises a real
    method (no mocks, name attributable, body calls the entity), min-tests is
    met, and coverage meets the threshold (best-effort: coverage is not allowed
    to trap the agent)."""

    def done_check(workspace: str):
        full = os.path.join(workspace, test_file)
        if not os.path.isfile(full):
            return False, f"{test_file} does not exist yet — write the test file first."
        content = open(full, encoding="utf-8", errors="replace").read()
        if not content.strip():
            return False, f"{test_file} is empty — write tests for the module under test."

        coverage, result = _run_suite(adapter, workspace, test_file, source_file,
                                      config.timeout_seconds)
        if result.total == 0:
            # The runner ran but the adapter could not parse a "N passed" summary.
            # If the output carries failure/error markers, treat it as failing
            # (the suite is not all-passing); otherwise it likely did not run.
            if _output_has_failures(result.output):
                return False, ("the suite has failing/erroring tests. Call run_tests "
                               "for the tracebacks and fix or remove them — the final "
                               "suite must be ALL-PASSING.")
            return False, ("no tests ran — the suite likely fails to compile/import. "
                           "Call run_tests to see the error, then fix it.")
        if not result.success:
            return False, (f"{result.failed} failing + {result.errors} erroring tests "
                           "remain. Call run_tests for the tracebacks and fix or remove "
                           "them — the final suite must be ALL-PASSING.")

        # Every test must REALLY exercise a real method (no mocks, attributable
        # name, body calls the entity) — otherwise phi is a false signal. Require
        # the agent to FIX these, not delete.
        if validator is not None:
            issues = validator(content)
            if issues:
                return False, (
                    f"{len(issues)} test-quality problem(s) must be fixed before done: "
                    + "; ".join(issues[:5]) + (" ..." if len(issues) > 5 else "")
                    + " Valid entities: " + _entity_examples(entities or []) + "."
                )

        if config.min_tests and _count_tests(language, content) < config.min_tests:
            have = _count_tests(language, content)
            return False, (f"only {have} tests; need at least {config.min_tests}. "
                           "Add more passing tests covering more behaviour.")

        # Coverage is best-effort: only block if the adapter actually measured it.
        if coverage is not None and coverage.total_lines > 0:
            if not coverage.meets_threshold(config.line_coverage_threshold,
                                            config.branch_coverage_threshold):
                return False, (
                    f"coverage line={coverage.line:.1%}/"
                    f"{config.line_coverage_threshold:.0%} "
                    f"branch={coverage.branch:.1%}/"
                    f"{config.branch_coverage_threshold:.0%} below target. "
                    "Add tests for the uncovered lines (call run_tests to see them).")

        return True, "all tests pass against the ground-truth source."

    return done_check


# --------------------------------------------------------------------------- #
# Role / task prompts
# --------------------------------------------------------------------------- #
_ROLE_BASE = """\
You are a test-authoring agent. Your sole job is to write a COMPLETE, ALL-PASSING \
{language} test suite for the module under test, in one test file ({test_file}).

Hard rules:
- The module under test is the REAL source in {source_file} — read it to learn \
the exact classes, methods, and signatures. Write tests that exercise its actual \
behaviour; do NOT guess APIs.
- CALL THE REAL CODE. Every test MUST import and invoke the real class/method \
under test. Do NOT define Mock/Fake/Stub/Dummy classes, and do NOT re-implement \
or shadow the class under test or its dependencies — a test that passes without \
calling the real code is WORTHLESS and will be rejected. The real dependency \
classes already exist on the classpath; construct inputs with them (e.g. for \
jsoup: `org.jsoup.Jsoup.parse(html)` for an Element, \
`org.jsoup.select.QueryParser.parse(css)` for an Evaluator) and then call the \
real target method (e.g. `Collector.collect(eval, root)`).
- LEARN THE DEPENDENCY APIs by reading their source. If a `repo_sources/` \
directory is present it holds the read-only source of every other file in the \
repo — use read_file/grep on it to find the exact way to construct the types \
the target needs and the real methods to call. Do NOT guess an API or invent a \
Mock when you can read the real one.
- run_tests runs your suite against this ground-truth source and reports \
pass/fail, coverage, and full tracebacks. Use it after every edit.
- Every test in the FINAL suite must PASS. When a test fails, FIX it — read the \
traceback and correct the wrong assertion, argument, import, or API usage. \
Prefer fixing; delete a test ONLY as a last resort when it genuinely cannot be \
made correct.
- NAME each test method `test_<ClassName>_<methodName>_<case>`, starting with the \
EXACT class and method it exercises (e.g. `test_Collector_collect_matching`, \
`test_Collector_findFirst_noMatch`). This is REQUIRED so each test is attributable \
to a real entity. run_tests reports any test whose name is NOT attributable — when \
it does, RENAME that test (do not delete it) to use a real class+method.
- {min_tests_rule}
- {coverage_rule}
- When run_tests shows all tests passing AND every test name is attributable \
(and the targets above are met), call done."""

_TASK = """\
Write a {language} test suite for the module in {source_file}, in {test_file}.

Workflow:
1. read_file {source_file} to learn the real classes, methods, and signatures.
2. write_file {test_file} with tests that import/use the module under test.
3. run_tests to see pass/fail, coverage, and tracebacks; edit_file to fix \
failures and add tests for uncovered lines; repeat.
4. When every test passes and the targets are met, call done.

run_tests executes against the real source, so a failing test means YOUR test is \
wrong (bad arg / wrong assertion / wrong import) — FIX it (prefer fixing over \
removing). If run_tests flags a test name as not attributable, RENAME it to \
`test_<ClassName>_<methodName>_<case>` using a real method."""


def _agents_md(source_file: str, test_file: str, language: str,
               config: TestGeneratorConfig, dep_ref: Optional[str] = None) -> str:
    """Project-context note injected into the agent's system prompt."""
    targets = []
    if config.min_tests:
        targets.append(f"- at least {config.min_tests} passing tests")
    targets.append(f"- line coverage >= {config.line_coverage_threshold:.0%} "
                   f"and branch coverage >= {config.branch_coverage_threshold:.0%} "
                   "(best-effort)")
    return (
        f"# Test-authoring workspace\n\n"
        f"Module under test: `{source_file}` ({language}) — READ-ONLY reference. "
        f"Read it to learn the real API; do not edit it.\n"
        f"Target test file: `{test_file}` — write ALL your tests here.\n\n"
        f"## Targets\n" + "\n".join(targets) + "\n\n"
        f"## Files here\n"
        f"- `{source_file}` — the real module under test (your source of truth).\n"
        f"- `{test_file}` — the test suite you write.\n"
        + (f"- `{dep_ref}/` — READ-ONLY source of EVERY OTHER file in the repo "
           f"(the target's dependencies). READ these to learn how to construct "
           f"inputs and call real APIs (e.g. how to build the types the target "
           f"takes/returns). Use read_file/grep on `{dep_ref}/` instead of "
           f"guessing or mocking.\n" if dep_ref else "")
        + f"- `AGENTS.md` — this note.\n\n"
        f"`run_tests` runs `{test_file}` against `{source_file}` and is your only "
        f"feedback tool. The final suite must be all-passing.\n"
    )


# --------------------------------------------------------------------------- #
# Final self-verification: keep only tests that PASS against the ground truth
# --------------------------------------------------------------------------- #
def _failing_test_names(output: str, language: str) -> set:
    """Names of failing/erroring test methods parsed from runner output."""
    names: set = set()
    if not output:
        return names
    if language == "java":
        # JUnit console (--details verbose): a result block carries
        # "methodName = 'X'" followed by a "status: FAILED/ABORTED/..." line.
        cur = None
        for line in output.splitlines():
            m = re.search(r"methodName\s*=\s*'([^']+)'", line)
            if m:
                cur = m.group(1)
            s = re.search(r"status:\s*(\w+)", line)
            if s and cur:
                if s.group(1).upper() in ("FAILED", "ABORTED", "ERROR"):
                    names.add(cur)
                cur = None
        # JUnit failure tree lines: "  test_x() ✘ ..."
        for m in re.finditer(r"\b(test\w+)\(\)\s*[✘✗x]", output):
            names.add(m.group(1))
    else:
        # pytest: "path::test_x FAILED/ERROR" and summary "FAILED path::test_x".
        for m in re.finditer(r"::(\w+)\s+(?:FAILED|ERROR)\b", output):
            names.add(m.group(1))
        for m in re.finditer(r"^(?:FAILED|ERROR)\s+\S+::(\w+)", output, re.MULTILINE):
            names.add(m.group(1))
    return names


def _remove_java_method(content: str, name: str) -> str:
    """Remove the (annotation-prefixed, brace-balanced) Java method ``name``."""
    pat = re.compile(
        r"(?:^[ \t]*@[\w.]+(?:\([^)]*\))?[ \t]*\n)*"
        r"[ \t]*[\w<>\[\], @.]*\b" + re.escape(name) + r"\s*\([^;{)]*\)[^{;]*\{",
        re.MULTILINE,
    )
    m = pat.search(content)
    if not m:
        return content
    start, j, depth, n = m.start(), m.end() - 1, 0, len(content)
    while j < n:
        c = content[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                j += 1
                break
        j += 1
    return content[:start].rstrip() + "\n\n" + content[j:].lstrip("\n")


def _extract_test_names(content: str, language: str) -> list:
    """Names of the test methods/functions declared in the suite."""
    if language == "java":
        return re.findall(r"\bvoid\s+(test\w+)\s*\(", content)
    return re.findall(r"^\s*def\s+(test\w+)\s*\(", content, re.MULTILINE)


def _is_method_entity(qualname: str) -> bool:
    """True for a method/constructor entity (dotted or 'ClassName constructor'),
    False for a bare class entity."""
    return ("." in qualname) or qualname.endswith(" constructor")


def _make_attributor(entities: list, language: str):
    """Return ``f(test_names) -> list[unattributable names]`` or ``None``.

    Resolves each test name to a REAL module entity (Java only; Python
    attribution is by file, not name) and requires METHOD-LEVEL attribution:
    a test that maps only to a bare class — when that class HAS method/
    constructor entities to target — is flagged so the agent renames it to
    exercise (and name) a specific method, giving a per-method phi signal
    instead of a single coarse class-level one. ``None`` when there is nothing
    to check against.
    """
    if not entities or language != "java":
        return None
    try:
        from docsearch.java_test_executor import JavaTestExecutor
    except Exception:
        return None
    ent_set = set(entities)
    # Classes that have at least one method/constructor entity — tests on these
    # must target a method, not the bare class.
    classes_with_methods = set()
    for e in entities:
        if "." in e:
            classes_with_methods.add(e.split(".", 1)[0])
        elif e.endswith(" constructor"):
            classes_with_methods.add(e.split(" ", 1)[0])
    attr = JavaTestExecutor(
        test_suite_path="/dev/null", target_module="x", repo_path=".",
        entities=entities,
    )

    def unattributable(names: list) -> list:
        bad = []
        for n in names:
            ent = attr._test_name_to_entity(n)
            if ent is None or ent not in ent_set:
                bad.append(n)
            elif not _is_method_entity(ent) and ent in classes_with_methods:
                # Mapped only to a class that has methods — too coarse.
                bad.append(n)
        return bad

    return unattributable


def _entity_examples(entities: list, limit: int = 8) -> str:
    """A few real dotted entity names to show the agent valid test targets."""
    dotted = [e for e in entities if "." in e]
    return ", ".join(dotted[:limit]) if dotted else ", ".join(entities[:limit])


# Mock/fake/stub helper classes let a test "pass" without touching the real code
# under test (a false phi signal) — they are forbidden.
_MOCK_CLASS = re.compile(r"\bclass\s+(Mock|Fake|Stub|Dummy)\w*", re.IGNORECASE)


def _java_test_methods(content: str) -> list:
    """Return ``[(name, body)]`` for each Java ``@Test void testX(){...}`` (body
    is the brace-balanced text including the braces)."""
    out = []
    for m in re.finditer(r"\bvoid\s+(test\w+)\s*\([^)]*\)\s*(?:throws[^{;]*)?\{", content):
        name = m.group(1)
        i = m.end() - 1
        depth, j, n = 0, m.end() - 1, len(content)
        while j < n:
            ch = content[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        out.append((name, content[i:j]))
    return out


def _make_test_validator(entities: list, language: str):
    """Return ``f(content) -> list[str]`` of problems, or ``None`` (Java + known
    entities only).

    Enforces that each test is REAL and method-targeted:
      * no Mock/Fake/Stub/Dummy helper classes (false-signal gaming);
      * each test name is attributable to a real METHOD/constructor entity;
      * each test BODY actually CALLS that entity (``method(`` for methods,
        ``new Class(`` for constructors) — so it exercises the real code, not a
        look-alike.
    """
    if not entities or language != "java":
        return None
    try:
        from docsearch.java_test_executor import JavaTestExecutor
    except Exception:
        return None
    ent_set = set(entities)
    classes_with_methods = set()
    for e in entities:
        if "." in e:
            classes_with_methods.add(e.split(".", 1)[0])
        elif e.endswith(" constructor"):
            classes_with_methods.add(e.split(" ", 1)[0])
    attr = JavaTestExecutor(
        test_suite_path="/dev/null", target_module="x", repo_path=".",
        entities=entities,
    )

    def validate(content: str) -> list:
        issues = []
        if _MOCK_CLASS.search(content):
            issues.append(
                "FORBIDDEN: the suite defines Mock/Fake/Stub/Dummy classes. Delete "
                "them and call the REAL classes from the classpath (e.g. "
                "org.jsoup.Jsoup.parse(...), org.jsoup.select.QueryParser.parse(...))."
            )
        for name, body in _java_test_methods(content):
            ent = attr._test_name_to_entity(name)
            if ent is None or ent not in ent_set:
                issues.append(f"{name}: name not attributable to a real entity — "
                              f"rename to test_<Class>_<method>_<case>.")
                continue
            if not _is_method_entity(ent) and ent in classes_with_methods:
                issues.append(f"{name}: maps only to class {ent} — target a specific method.")
                continue
            # Body must actually invoke the attributed entity.
            if ent.endswith(" constructor"):
                cls = ent.split(" ", 1)[0]
                if not re.search(r"\bnew\s+" + re.escape(cls) + r"\s*\(", body):
                    issues.append(f"{name}: body never does `new {cls}(...)` — "
                                  f"it must construct the real object, not a mock.")
            else:
                meth = ent.split(".", 1)[1]
                if not re.search(r"\b" + re.escape(meth) + r"\s*\(", body):
                    issues.append(f"{name}: body never calls {ent}(...) — it must "
                                  f"invoke the REAL method, not a mock/look-alike.")
        return issues

    return validate


def _remove_python_func(content: str, name: str) -> str:
    """Remove the Python ``def name(...)`` block (and any decorators above it)."""
    lines = content.splitlines(keepends=True)
    out: list = []
    i, n = 0, len(lines)
    while i < n:
        m = re.match(r"([ \t]*)def\s+" + re.escape(name) + r"\s*\(", lines[i])
        if m:
            indent = len(m.group(1))
            while out and re.match(r"[ \t]*@", out[-1]):
                out.pop()
            i += 1
            while i < n and (lines[i].strip() == ""
                             or len(lines[i]) - len(lines[i].lstrip()) > indent):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "".join(out)


# --------------------------------------------------------------------------- #
# The ReAct test generator
# --------------------------------------------------------------------------- #
class ReactTestGenerator:
    """A ReAct-agent-backed test-suite generator.

    The agent works in a private temporary workspace containing the REAL source
    (read-only reference), an ``AGENTS.md`` role note, and the (initially
    skeleton) test file. Its single feedback tool runs the suite against the
    ground-truth source via the project's :class:`LanguageAdapter`.
    """

    def __init__(
        self,
        config: Optional[TestGeneratorConfig] = None,
        dependency_classpath: str = "",
        target_package: str = "",
        repo_root: Optional[str] = None,
        entities: Optional[list] = None,
    ):
        """
        Args:
            config: reuse :class:`TestGeneratorConfig` — model, coverage
                thresholds, ``max_iterations`` (mapped to a turn budget),
                ``min_tests``, ``timeout_seconds``, ``verbose``.
            dependency_classpath: The repo closure ``deps_classpath``
                (ground-truth classes dir + external jars), e.g.
                ``RepoClosure.deps_classpath``. When set (Java), the generated
                tests are compiled and run against the GROUND-TRUTH target file
                plus this closure rather than in an isolated default-package
                temp project. Empty preserves today's self-contained flow.
            target_package: Java package of the target file (e.g.
                ``"org.jsoup.select"``). Used to place the read-only target
                source — and the generated test — under their package directory
                so the agent reads the real signatures and javac/JUnit see
                package-structured classes. Empty means the default package.
            repo_root: Repository root of the closure (threaded to the adapter
                for JUnit-jar resolution). Empty/None for the self-contained
                flow.
        """
        self.config = config or TestGeneratorConfig()
        self.dependency_classpath = dependency_classpath
        self.target_package = target_package
        self.repo_root = repo_root
        # Real module entity qualnames (e.g. ["Collector.collect", ...]). When
        # given, the verification ALSO requires every test name to be
        # attributable to one of these — so the agent renames unattributable
        # tests rather than leaving them (a passing-but-unattributable test
        # yields no phi signal downstream).
        self.entities = list(entities) if entities else []
        self._adapters: dict[Language, LanguageAdapter] = {}

    def generate(
        self,
        source_file: str | Path,
        output_file: Optional[str | Path] = None,
        language: Optional[str] = None,
        artifact_dir: Optional[str | Path] = None,
    ) -> TestSuite:
        """Generate an all-passing test suite for ``source_file`` via the ReAct loop.

        Returns a :class:`TestSuite`; writes the suite to ``output_file`` when
        given (preserving the existing CLI write/print behavior).

        When ``artifact_dir`` is given, the agent's COMPLETE state is persisted
        there: its workspace (``testgen_workspace/`` — the module-under-test
        reference, AGENTS.md, and the evolving test file the agent edits) and a
        ``testgen_session.jsonl`` event log of every loop step (tool calls,
        tool results / run_tests feedback, assistant messages). The ReAct agent
        plus its filesystem IS the full state, so persisting both makes the run
        fully auditable/replayable rather than discarded in a temp dir.
        """
        source_path = Path(source_file)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_file}")

        lang = self._detect_language(source_path, language)
        if self.config.verbose:
            print(f"Detected language: {lang.value}")
        adapter = self._get_adapter(lang)
        lang_str = lang.value

        test_base = _test_filename(adapter, source_path)
        source_base = _source_basename(source_path)

        # For real repos the target lives in a Java package: read the package off
        # the source (falling back to the caller-supplied target_package) and
        # place BOTH the read-only target and the generated test under their
        # package directory so javac/JUnit see package-structured classes and the
        # agent reads the real, package-qualified signatures. Empty package keeps
        # the flat default-package layout. (Python: always flat.)
        if lang == Language.JAVA:
            package = (_java_package(source_path.read_text(encoding="utf-8",
                                                            errors="replace"))
                       or self.target_package)
        else:
            package = ""
        source_name = _packaged_relpath(source_base, package)
        test_file = _packaged_relpath(test_base, package)

        # 1) Workspace: the REAL source (read-only ref), AGENTS.md, skeleton test
        #    file. Persist it under artifact_dir when given (the agent's
        #    filesystem IS its state) — otherwise a throwaway temp dir.
        session_path = None
        if artifact_dir is not None:
            artifact_dir = Path(artifact_dir)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            workspace = str(artifact_dir / "testgen_workspace")
            os.makedirs(workspace, exist_ok=True)
            session_path = str(artifact_dir / "testgen_session.jsonl")
        else:
            workspace = tempfile.mkdtemp(prefix="testgen_")
        source_dest = os.path.join(workspace, source_name)
        os.makedirs(os.path.dirname(source_dest) or workspace, exist_ok=True)
        shutil.copy(source_path, source_dest)

        # Dependency-source visibility: copy the repo's OTHER source files into a
        # read-only `repo_sources/` reference dir so the agent can READ the real
        # APIs of the target's dependencies (e.g. how to build an Element via
        # Jsoup.parse, what QueryParser.parse returns). Without this the agent
        # only sees the target file, cannot learn the dependency APIs, and
        # resorts to mocks/reflection hacks. (Reference only — not compiled.)
        dep_ref = None
        if self.repo_root:
            ext = ".java" if lang == Language.JAVA else ".py"
            dep_root = Path(self.repo_root)
            dep_ref = "repo_sources"
            copied = 0
            for f in dep_root.rglob(f"*{ext}"):
                if any(p in (".git", "target", "build", "out", "__pycache__",
                             ".mvn", ".gradle", "bin") for p in f.parts):
                    continue
                try:
                    rel = f.relative_to(dep_root)
                except ValueError:
                    continue
                dest = Path(workspace) / dep_ref / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy(f, dest)
                    copied += 1
                except OSError:
                    pass
                if copied >= 1500:  # safety cap for very large repos
                    break

        with open(os.path.join(workspace, "AGENTS.md"), "w", encoding="utf-8") as f:
            f.write(_agents_md(source_name, test_file, lang_str, self.config, dep_ref))
        test_dest = os.path.join(workspace, test_file)
        os.makedirs(os.path.dirname(test_dest) or workspace, exist_ok=True)
        with open(test_dest, "w", encoding="utf-8") as f:
            f.write(self._skeleton(lang, source_path, package))

        # Test validator (Java + known entities): each test must have an
        # attributable METHOD name, actually CALL that real method, and use no
        # mock/fake classes — so the agent writes real, method-targeted tests.
        validator = _make_test_validator(self.entities, lang_str)

        # 2) Tools: rich primitives + the single run_tests feedback Tool.
        run_tests = _make_run_tests_tool(
            adapter, lang_str, test_file, source_name, self.config.timeout_seconds,
            validator=validator, entities=self.entities,
        )
        tools = default_tools()
        tools[run_tests.name] = run_tests

        # 3) done is gated on the real termination contract.
        done_check = _make_done_check(
            adapter, lang_str, test_file, source_name, self.config,
            validator=validator, entities=self.entities,
        )

        # 4) Drive the director loop. Budget is GENEROUS on purpose: authoring a
        #    real, all-passing suite for a cross-package class needs many turns
        #    (discover the API, write tests, fix compile/assertion errors against
        #    the closure). Turns are cheap relative to a wasted run, so we give a
        #    high floor rather than cutting the agent off mid-convergence.
        budget = max(60, self.config.max_iterations * 12)
        min_tests_rule = (
            f"Write at least {self.config.min_tests} passing tests."
            if self.config.min_tests else "Cover the module's behaviour thoroughly."
        )
        coverage_rule = (
            f"Aim for line coverage >= {self.config.line_coverage_threshold:.0%} "
            f"and branch coverage >= {self.config.branch_coverage_threshold:.0%}."
        )
        if self.config.verbose:
            print("Starting ReAct test-generation loop...")
        make_llm = make_testgen_llm
        llm = make_llm(self.config.llm_model)
        result = run_agent(
            llm=llm,
            model=llm.model,
            workspace=workspace,
            role_base=_ROLE_BASE.format(
                language=lang_str, test_file=test_file, source_file=source_name,
                min_tests_rule=min_tests_rule, coverage_rule=coverage_rule,
            ),
            task=_TASK.format(
                language=lang_str, test_file=test_file, source_file=source_name,
            ),
            tools=tools,
            budget=budget,
            tag="testgen",
            done_check=done_check,
            session_path=session_path,  # JSONL event log of the whole loop
            # Iterating with run_tests legitimately calls the same tool many
            # times in a row; raise the circuit breaker so the agent is not cut
            # off mid-convergence, and allow a few more no-act nudges.
            max_same_tool=40,
            max_no_act=6,
        )
        if self.config.verbose:
            print(f"Agent stopped: {result.stop_reason} after {result.turns} turns")

        # 5) Read back the final suite.
        test_path = os.path.join(workspace, test_file)
        try:
            with open(test_path, encoding="utf-8", errors="replace") as f:
                test_content = _strip_code_fences(f.read()) + "\n"
        except OSError:
            test_content = ""

        # 5b) FINAL SELF-VERIFICATION (unconditional): confirm the SUBMITTED
        #     suite is all-passing on the ground truth AND every test name is
        #     attributable to a real entity. Fixing is the AGENT's job (driven by
        #     the run_tests feedback + done_check during the loop); this step does
        #     NOT mutate tests — it only verifies. If the contract is not met
        #     (e.g. the agent stopped on budget), the suite is rejected (empty)
        #     so unverified tests never leak downstream.
        test_content = self._final_verify(
            adapter, workspace, test_file, source_name, lang_str, test_content,
            validator,
        )
        if not test_content.strip():
            if self.config.verbose:
                print("Final verification: no all-passing tests — returning empty suite.")
            return TestSuite(
                module_name=source_path.stem, language=lang,
                test_file_content="", test_cases=[], coverage=None,
                source_file=str(source_path), test_file_path="",
            )

        coverage, final_result = _run_suite(
            adapter, workspace, test_file, source_name, self.config.timeout_seconds
        )

        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if self.config.verbose:
                print(f"\nWriting tests to {output_path}")
            output_path.write_text(test_content)
        else:
            # No explicit destination: the suite already exists (written by the
            # agent) at the workspace test path. Point test_file_path at THAT
            # real, written file rather than an unwritten path beside the source —
            # callers (e.g. the repo driver) rely on test_file_path existing, and
            # writing beside the source would pollute the repo.
            output_path = Path(test_path)

        test_suite = TestSuite(
            module_name=source_path.stem,
            language=lang,
            test_file_content=test_content,
            test_cases=[],
            coverage=coverage,
            source_file=str(source_path),
            test_file_path=str(output_path),
        )

        if self.config.verbose:
            self._print_summary(test_suite, final_result)

        return test_suite

    # ----------------------------------------------------------------------- #
    # Final self-verification (verify only — fixing is the agent's job)
    # ----------------------------------------------------------------------- #
    def _final_verify(self, adapter, workspace, test_file, source_file,
                      language, content: str, validator) -> str:
        """Verify the submitted suite is all-passing on the ground truth AND
        every test really exercises a real method (attributable name, no mocks,
        body calls the entity).

        This does NOT mutate the suite — the agent is responsible for FIXING
        problems during its loop (the run_tests feedback and done_check drive
        that). Here we only render the verdict: return the verified content if
        the contract holds, else ``""`` so an unverified/gamed suite is skipped
        rather than leaking a false phi signal downstream.
        """
        if not content.strip():
            return ""
        _, res = _run_suite(adapter, workspace, test_file, source_file,
                            self.config.timeout_seconds)
        if not (res.total > 0 and res.success):
            if self.config.verbose:
                print("Final verification: suite is not all-passing — rejecting.")
            return ""
        if validator is not None:
            issues = validator(content)
            if issues:
                if self.config.verbose:
                    print(f"Final verification: {len(issues)} test-quality "
                          f"problem(s) ({issues[:3]}) — rejecting.")
                return ""
        return content

    # ----------------------------------------------------------------------- #
    # Workspace skeleton (import-smoke starter so run_tests has something to run)
    # ----------------------------------------------------------------------- #
    def _skeleton(self, language: Language, source_path: Path,
                  package: str = "") -> str:
        if language == Language.PYTHON:
            module = source_path.stem
            return (
                f'"""Tests for {module}.py"""\n\n'
                "import pytest\n"
                f"from {module} import *  # noqa: F401,F403\n\n\n"
                "def test_import_smoke():\n"
                f"    import {module}  # noqa: F401\n"
            )
        # Java — emit the SAME package as the target so the test sits in-package
        # (it can reference package-private members) and compiles under its
        # package dir against the closure.
        class_name = source_path.stem
        package_decl = f"package {package};\n\n" if package else ""
        return (
            f"{package_decl}"
            f"// Tests for {class_name}.java\n\n"
            "import org.junit.jupiter.api.Test;\n"
            "import static org.junit.jupiter.api.Assertions.*;\n\n"
            f"class {class_name}Test {{\n\n"
            "    @Test\n"
            "    void importSmoke() {\n"
            "        assertTrue(true);\n"
            "    }\n"
            "}\n"
        )

    # ----------------------------------------------------------------------- #
    # Shared helpers (mirroring TestGenerator)
    # ----------------------------------------------------------------------- #
    def _detect_language(
        self, source_path: Path, language_override: Optional[str]
    ) -> Language:
        if language_override:
            lang_lower = language_override.lower()
            if lang_lower == "python":
                return Language.PYTHON
            elif lang_lower == "java":
                return Language.JAVA
            else:
                raise ValueError(f"Unsupported language: {language_override}")

        ext = source_path.suffix.lower()
        if ext == ".py":
            return Language.PYTHON
        elif ext == ".java":
            return Language.JAVA
        raise ValueError(
            f"Cannot determine language from extension: {ext}. "
            "Please specify --language explicitly."
        )

    def _get_adapter(self, language: Language) -> LanguageAdapter:
        if language not in self._adapters:
            if language == Language.PYTHON:
                self._adapters[language] = PythonAdapter()
            elif language == Language.JAVA:
                # Thread the repo closure through so the Java adapter compiles &
                # runs generated tests against the ground-truth target + closure.
                self._adapters[language] = JavaAdapter(
                    dependency_classpath=self.dependency_classpath,
                    target_package=self.target_package,
                    repo_root=self.repo_root,
                )
        return self._adapters[language]

    def _print_summary(self, test_suite: TestSuite, result: TestResult) -> None:
        print("\n" + "=" * 50)
        print("TEST GENERATION SUMMARY (ReAct)")
        print("=" * 50)
        print(f"Module: {test_suite.module_name}")
        print(f"Language: {test_suite.language.value}")
        print(f"Tests: {_count_tests(test_suite.language.value, test_suite.test_file_content)}")
        print(f"Result: {result.passed} passed, {result.failed} failed, "
              f"{result.errors} errors")
        if test_suite.coverage:
            cov = test_suite.coverage
            print(f"\nCoverage:")
            print(f"  Line: {cov.line:.1%} ({cov.covered_lines}/{cov.total_lines})")
            print(f"  Branch: {cov.branch:.1%} "
                  f"({cov.covered_branches}/{cov.total_branches})")
        print(f"\nOutput: {test_suite.test_file_path}")
        print("=" * 50)
