"""A :class:`~docsearch.search.contracts.CodeGenerator` driven by the generic
ReAct runtime in ``agent/``.

The search loop hands this generator a :class:`~docsearch.search.model.Module`
plus the current per-entity documentation and asks for one full implementation
of the module. Instead of a single completion, this generator runs the director
loop (:func:`agent.runtime.run_agent`) over a private workspace: the agent reads the
documentation spec, writes the target source file, and iterates against a
COMPILE/SMOKE feedback tool until the file compiles/imports cleanly.

phi SIGNAL PROTECTION (non-negotiable): the only feedback channel registered for
the agent is the compile/smoke tool. It runs ``javac`` (Java) or a
compile+import (Python) on the target file *alone* and returns only
syntax/compiler/import errors. The agent is never given the evaluation test
suite, the evaluator, or any path to them — its workspace contains nothing but
the spec, an ``AGENTS.md`` role note, and the target file. phi is measured
elsewhere by the :class:`~docsearch.search.contracts.Evaluator` on hidden tests.
Leaking those tests here would drive phi to 1.0 and destroy the search.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from typing import Mapping, Optional

from docsearch.agent.runtime import run_agent
from docsearch.agent.tools import Tool, default_tools

from docsearch.pipeline.entities import Module

logger = logging.getLogger(__name__)

# javac error lines look like "Foo.java:12: error: ...".
_JAVAC_ERROR = re.compile(r"^\S+\.java:\d+:\s*error:", re.MULTILINE)
_PUBLIC_CLASS = re.compile(r"public\s+(?:final\s+|abstract\s+)?class\s+(\w+)")
_ANY_CLASS = re.compile(r"\bclass\s+(\w+)")

# Match the project's executor default so we use the same JDK everywhere.
_DEFAULT_JDK_PATH = "/usr/lib/jvm/jdk-11.0.0.1"

_FENCE_OPEN = re.compile(r"^\s*```(?:java|python|py)?\s*\n?", re.IGNORECASE)
_FENCE_CLOSE = re.compile(r"\n?```\s*$")


def _strip_code_fences(text: str) -> str:
    """Remove a single leading/trailing markdown fence if the agent left one."""
    if not text:
        return ""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _FENCE_OPEN.sub("", stripped, count=1)
        stripped = _FENCE_CLOSE.sub("", stripped)
    return stripped.strip()


def _find_tool(name: str) -> str:
    """Resolve ``javac``/``java``/``python`` using the project's JDK convention.

    Prefers ``$JAVA_HOME/bin`` (the Java executor's primary source), then the
    project's default JDK path, then ``PATH``.
    """
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        candidate = os.path.join(java_home, "bin", name)
        if os.path.isfile(candidate):
            return candidate
    candidate = os.path.join(_DEFAULT_JDK_PATH, "bin", name)
    if os.path.isfile(candidate):
        return candidate
    return shutil.which(name) or name


# --------------------------------------------------------------------------- #
# Spec rendering — the agent's read-only source of truth
# --------------------------------------------------------------------------- #
def render_documentation(module: Module, docs: Mapping[str, str]) -> str:
    """Format the per-entity documentation spec (reference ``render_documentation``).

    One block per entity: ``### <qualname> (<kind>)`` + signature + declared
    fields (for classes) + the doc. The fields are the interface contract the
    implementation must reproduce so white-box tests that access fields
    directly compile; they are not behavioral and do not leak the hidden tests.
    """
    lines: list[str] = []
    for qualname, entity in module.entities.items():
        doc = docs.get(qualname, "")
        lines.append(f"### {qualname} ({entity.kind.value})")
        if entity.signature:
            lines.append(f"Signature: {entity.signature}")
        if entity.fields:
            lines.append("Declared fields (reproduce these exactly):")
            for field_line in entity.fields:
                lines.append(f"  {field_line}")
        lines.append("Documentation:")
        lines.append(doc.strip() or "(empty)")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# Target file naming
# --------------------------------------------------------------------------- #
def _java_class_name(module: Module) -> str:
    """Best guess at the public class the generated Java file must define.

    javac requires the filename to match the public class, so we derive the
    name from the original source (preferred) or the module name. Class-kind
    entity qualnames are simple class names, so the module's own name is the
    reliable fallback.
    """
    for pat in (_PUBLIC_CLASS, _ANY_CLASS):
        m = pat.search(module.source or "")
        if m:
            return m.group(1)
    # Fall back to a class-kind entity, then the module name.
    name = module.name.split(".")[-1].replace("-", "_")
    return name or "Solution"


def _target_filename(module: Module, language: str, target_package: str = "") -> str:
    """Workspace-relative path of the target source file.

    For packaged Java files (multi-file repos) the file must live under its
    package directory so its ``package ...;`` line and the ``javac`` output
    layout agree; e.g. package ``org.jsoup.select`` -> ``org/jsoup/select/
    Selector.java``. The single-file / default-package case is unchanged.
    """
    if language == "java":
        filename = f"{_java_class_name(module)}.java"
        if target_package:
            pkg_dir = target_package.replace(".", os.sep)
            return os.path.join(pkg_dir, filename)
        return filename
    return "module_under_test.py"


# --------------------------------------------------------------------------- #
# COMPILE/SMOKE feedback tools (the ONLY feedback the agent gets)
# --------------------------------------------------------------------------- #
def _make_java_smoke_tool(
    target: str, *, dependency_classpath: str = "", timeout: int = 60
) -> Tool:
    """A feedback tool that runs ``javac`` on the target file alone.

    Returns compiler diagnostics only — no JUnit, no evaluation tests. When
    ``dependency_classpath`` is set (multi-file repo support) it is passed via
    ``javac -cp`` so the generated file's references to *other* repo classes
    (``Element``, etc.) resolve against the ground-truth dependency closure;
    the target itself is still the only file compiled — no tests, no JUnit, no
    evaluator. With no classpath the target compiles in isolation against the
    JDK and cross-type references surface as ordinary "cannot find symbol"
    diagnostics (acceptable smoke signal for self-contained single files).
    """
    javac = _find_tool("javac")

    def run(workspace: str, args: dict) -> str:
        full = os.path.join(workspace, target)
        if not os.path.isfile(full):
            return f"compile error: target file {target} does not exist yet — write it first"
        if not open(full, encoding="utf-8", errors="replace").read().strip():
            return f"compile error: {target} is empty — implement every entity from the spec"
        cmd = [javac]
        if dependency_classpath:
            cmd += ["-cp", dependency_classpath]
        cmd += ["-d", workspace, full]
        try:
            proc = subprocess.run(
                cmd,
                cwd=workspace, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"javac timed out after {timeout}s"
        except OSError as exc:
            return f"could not run javac: {exc}"
        if proc.returncode == 0:
            return "OK: compiles cleanly (javac, no errors)."
        return "javac errors:\n" + (proc.stderr.strip() or proc.stdout.strip() or "(no diagnostics)")

    return Tool(
        name="compile_check",
        description=(
            "Run javac on the target Java file ALONE and return compiler "
            "errors (syntax / cannot-find-symbol / type errors). This is your "
            "ONLY feedback channel: there is no test runner and you cannot see "
            "any grading tests. Use it after each edit to confirm the file "
            "compiles."
        ),
        input_schema={"type": "object", "properties": {}},
        run=run,
        kind="feedback",
    )


def _make_python_smoke_tool(target: str, *, timeout: int = 60) -> Tool:
    """A feedback tool that compiles then imports the target Python file alone.

    Returns syntax/import errors only — no pytest, no evaluation tests.
    """
    python = _find_tool("python") if not shutil.which("python3") else _find_tool("python3")

    def run(workspace: str, args: dict) -> str:
        full = os.path.join(workspace, target)
        if not os.path.isfile(full):
            return f"import error: target file {target} does not exist yet — write it first"
        if not open(full, encoding="utf-8", errors="replace").read().strip():
            return f"import error: {target} is empty — implement every entity from the spec"
        mod = os.path.splitext(target)[0]
        # compile() for syntax, then import the module to catch import-time crashes.
        snippet = (
            "import importlib, py_compile, sys, traceback\n"
            f"py_compile.compile({mod!r} + '.py', doraise=True)\n"
            "sys.path.insert(0, '.')\n"
            "try:\n"
            f"    importlib.import_module({mod!r})\n"
            "except Exception:\n"
            "    traceback.print_exc(); sys.exit(1)\n"
            "print('OK')\n"
        )
        try:
            proc = subprocess.run(
                [python, "-c", snippet],
                cwd=workspace, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"smoke check timed out after {timeout}s"
        except OSError as exc:
            return f"could not run python: {exc}"
        if proc.returncode == 0:
            return "OK: compiles and imports cleanly (no syntax/import errors)."
        return "syntax/import errors:\n" + (proc.stderr.strip() or proc.stdout.strip() or "(no diagnostics)")

    return Tool(
        name="compile_check",
        description=(
            "Compile and import the target Python file ALONE and return any "
            "syntax or import errors. This is your ONLY feedback channel: there "
            "is no pytest run and you cannot see any grading tests. Use it after "
            "each edit to confirm the file imports without crashing."
        ),
        input_schema={"type": "object", "properties": {}},
        run=run,
        kind="feedback",
    )


def _make_smoke_tool(
    language: str, target: str, *, dependency_classpath: str = ""
) -> Tool:
    if language == "java":
        return _make_java_smoke_tool(target, dependency_classpath=dependency_classpath)
    return _make_python_smoke_tool(target)


def _make_done_check(language: str, target: str, smoke: Tool):
    """``done`` is accepted only when the target file exists, is non-empty, and
    passes the same compile/smoke check the agent has been using."""

    def done_check(workspace: str):
        full = os.path.join(workspace, target)
        if not os.path.isfile(full):
            return False, f"{target} does not exist yet."
        if not open(full, encoding="utf-8", errors="replace").read().strip():
            return False, f"{target} is empty — implement every entity from the spec."
        result = smoke.run(workspace, {})
        ok = result.startswith("OK")
        return ok, ("compiles cleanly." if ok else result)

    return done_check


# --------------------------------------------------------------------------- #
# Role / task prompts
# --------------------------------------------------------------------------- #
_ROLE_BASE = """\
You are a code-generation agent. Your sole job is to implement EVERY entity \
described in the documentation spec, ALONE, in one {language} source file \
({target}).

Hard rules:
- Implement the entities strictly from the documentation in spec.md. Do not add \
behaviour the docs do not describe.
- You may ONLY use the compile_check tool for feedback. There is NO test runner \
available to you and you CANNOT see the grading tests — they are hidden from you \
on purpose. Do not look for, ask for, or fabricate tests.
- Keep everything in the single target file {target}; make it self-contained so \
compile_check can verify it in isolation.
- When the target file implements every entity and compile_check reports OK, call \
done."""

_TASK = """\
{target} ALREADY CONTAINS A COMPLETE DRAFT implementation generated from the \
spec. Your job is to make it COMPILE and be faithful to the spec — not to \
rewrite it from scratch.

Workflow:
1. compile_check FIRST to see the current draft's compiler errors.
2. For each error, fix it with edit_file. When an error is an unresolved symbol \
from another package, consult `repo_sources/` (when present) to find that \
dependency's exact package / method signature, then fix the import or call. \
Only read repo_sources to resolve a SPECIFIC symbol — do not browse it broadly.
3. Verify every documented entity, including EVERY overloaded signature, is \
present in {target}; add any the draft is missing.
4. When compile_check reports OK and all entities/overloads are implemented, \
call done.

Remember: compile_check is your only feedback. You cannot see the grading tests. \
Budget is limited — spend it fixing compile errors, not browsing. Never leave \
{target} empty."""


class AgentCodeGenerator:
    """A ReAct-agent-backed :class:`contracts.CodeGenerator`.

    The agent works in a private temporary workspace containing only the spec,
    an ``AGENTS.md`` role note, and the (initially empty) target file. Its sole
    feedback tool is a compile/smoke check on that file — it has no access to
    the evaluator or its hidden test suite (phi protection).
    """

    def __init__(
        self,
        llm,
        *,
        language: str,
        budget: int = 12,
        workdir: Optional[str] = None,
        dependency_classpath: str = "",
        target_package: str = "",
        artifact_dir: Optional[str] = None,
        repo_root: Optional[str] = None,
        target_rel: Optional[str] = None,
    ):
        """
        Args:
            llm: a ``SearchLLM`` (exposes ``chat_step`` and carries ``.model``).
            language: ``"java"`` (primary) or ``"python"``.
            budget: max director-loop turns per generation.
            workdir: optional parent dir for the per-call workspace; defaults to
                a system temp dir. Each ``generate`` call gets a fresh subdir.
            dependency_classpath: (multi-file repos, Java) the ground-truth
                dependency closure classpath. When set, ``compile_check`` runs
                ``javac -cp <dependency_classpath>`` so the generated target's
                references to other repo classes resolve against the closure.
                Still compile-only — no tests/JUnit/evaluator (phi protection).
            target_package: (multi-file repos, Java) the Java package of the
                target file (e.g. ``"org.jsoup.select"``). When set, the target
                is placed under its package directory and keeps its
                ``package ...;`` line; dependency classes already exist on the
                classpath and must not be re-declared.
        """
        self.llm = llm
        self.language = (language or "python").lower()
        if self.language not in ("java", "python"):
            raise ValueError(f"unsupported language: {language!r}")
        self.budget = budget
        self.workdir = workdir
        self.dependency_classpath = dependency_classpath or ""
        self.target_package = target_package or ""
        # Dependency-source visibility (multi-file repos): when ``repo_root`` is
        # set, generate() copies the repo's OTHER source files into a read-only
        # ``repo_sources/`` reference dir so the agent can READ the real APIs of
        # its dependencies (where ``StringUtil`` lives, what ``Element`` exposes)
        # instead of GUESSING package paths — guessing is the dominant cause of
        # non-compiling reconstructions (and thus phi=0). This is phi-safe: the
        # eval TESTS are never in the repo source tree. CRITICAL anti-cheat:
        # ``target_rel`` (the target file's repo-relative path) and the repo's
        # own test tree are EXCLUDED, so the agent can never read the
        # ground-truth implementation it is supposed to reconstruct from docs.
        self.repo_root = repo_root
        self.target_rel = (target_rel or "").replace("\\", "/").lstrip("/")
        # When set, every generate() call persists its agent state (workspace +
        # session JSONL) under <artifact_dir>/codegen_runs/<n>/ instead of a
        # throwaway temp dir — the ReAct agent + its filesystem is the full
        # state, so it is auditable/replayable. generate() is called once per
        # search candidate, hence the per-run counter.
        self.artifact_dir = artifact_dir
        self._run_counter = 0

    def generate(self, module: Module, docs: Mapping[str, str]) -> str:
        """Synthesize a full implementation of ``module`` from ``docs`` alone."""
        target = _target_filename(module, self.language, self.target_package)
        session_path = None
        if self.artifact_dir is not None:
            run_dir = os.path.join(self.artifact_dir, "codegen_runs",
                                   f"run_{self._run_counter}")
            self._run_counter += 1
            workspace = os.path.join(run_dir, "workspace")
            os.makedirs(workspace, exist_ok=True)
            session_path = os.path.join(run_dir, "session.jsonl")
        else:
            workspace = tempfile.mkdtemp(prefix="codegen_", dir=self.workdir)

        # 1) Workspace: spec.md (rendered docs), AGENTS.md (role note), empty target.
        #    The target may live under a package directory (multi-file repos),
        #    so create its parent first.
        target_full = os.path.join(workspace, target)
        os.makedirs(os.path.dirname(target_full) or workspace, exist_ok=True)

        # 1a) Dependency-source visibility: copy the repo's OTHER source files
        #     into a read-only `repo_sources/` so the agent can READ real
        #     dependency APIs instead of guessing package paths. EXCLUDES the
        #     target file (anti-cheat: it must reconstruct from docs, not copy
        #     ground truth) and the repo's own test tree (phi protection + no
        #     behavior leakage). Reference only — not on the compile classpath
        #     (deps resolve via the precompiled closure).
        dep_copied = self._copy_repo_sources(workspace)

        with open(os.path.join(workspace, "spec.md"), "w", encoding="utf-8") as f:
            f.write(f"# Documentation spec for module: {module.name}\n\n")
            f.write(render_documentation(module, docs))
            note = _dependency_note(self.dependency_classpath, self.target_package)
            if note:
                f.write("\n" + note)
        with open(os.path.join(workspace, "AGENTS.md"), "w", encoding="utf-8") as f:
            f.write(_agents_md(module, target, self.language, self.target_package,
                               has_repo_sources=dep_copied > 0))

        # 1b) SEED the target with a one-shot draft generated directly from the
        #     spec, instead of starting empty. A reasoning agent given a large
        #     repo_sources/ tree tends to over-explore and can exhaust its budget
        #     reading without ever writing — leaving the target empty (phi=0).
        #     Seeding guarantees a real reconstruction always exists; the agent's
        #     job becomes compile-FIX (cheap, focused) rather than write-from-
        #     scratch, and if it wanders the draft still stands.
        draft = self._oneshot_draft(module, docs, target)
        with open(target_full, "w", encoding="utf-8") as f:
            f.write(draft)

        # 2) Tools: the rich primitives + the COMPILE/SMOKE feedback tool ONLY.
        #    No evaluator, no test suite, no run_eval — nothing test-aware.
        #    With a dependency closure, compile_check resolves repo deps via
        #    javac -cp (still compile-only — no tests).
        smoke = _make_smoke_tool(
            self.language, target, dependency_classpath=self.dependency_classpath
        )
        tools = default_tools()
        tools[smoke.name] = smoke

        # 3) done is gated on the target compiling/importing cleanly.
        done_check = _make_done_check(self.language, target, smoke)

        # 4) Drive the director loop, then return the final target file.
        run_agent(
            llm=self.llm,
            model=self.llm.model,
            workspace=workspace,
            role_base=_ROLE_BASE.format(language=self.language, target=target),
            task=_TASK.format(language=self.language, target=target),
            tools=tools,
            budget=self.budget,
            tag="codegen",
            done_check=done_check,
            session_path=session_path,  # JSONL event log of this codegen loop
        )

        target_path = os.path.join(workspace, target)
        try:
            with open(target_path, encoding="utf-8", errors="replace") as f:
                code = _strip_code_fences(f.read()).strip()
        except OSError:
            code = ""
        # If the agent emptied/never-touched the target, fall back to the seeded
        # one-shot draft so we never return empty (which would score phi=0).
        if not code:
            code = _strip_code_fences(draft).strip()
        return (code + "\n") if code else ""

    def _oneshot_draft(self, module, docs, target: str) -> str:
        """Generate a full target-file draft from the spec in ONE LLM call.

        Used to seed the agent's workspace (and as the final fallback). No
        compile feedback here — it is the agent's job to compile-fix this draft —
        but it guarantees a complete, non-empty reconstruction attempt that
        implements every documented entity and overload.
        """
        spec = render_documentation(module, docs)
        note = _dependency_note(self.dependency_classpath, self.target_package)
        prompt = (
            f"Implement EVERY entity documented below in a SINGLE {self.language} "
            f"source file ({target}). Implement every method and EVERY overloaded "
            f"signature exactly as documented. Output ONLY the complete source of "
            f"{target} — no prose, no explanations, no markdown fences.\n\n"
            + (note + "\n" if note else "")
            + spec
        )
        try:
            out = self.llm.complete(prompt, temperature=0).text
        except Exception as exc:  # never abort codegen for a draft failure
            logger.warning("one-shot draft generation failed: %s", exc)
            return ""
        return _strip_code_fences(out or "").strip()

    # Directory names never copied into repo_sources (build output / VCS).
    _SKIP_PARTS = {".git", "target", "build", "out", "__pycache__",
                   ".mvn", ".gradle", "bin", "node_modules"}

    def _copy_repo_sources(self, workspace: str) -> int:
        """Mirror the repo's dependency source files into ``workspace/repo_sources/``.

        Returns the number of files copied. Skips (a) when no ``repo_root`` is
        configured, (b) build/VCS dirs, (c) the repo's own test tree (any path
        with a ``test``/``tests`` segment — phi protection + no behavior leak),
        and (d) the TARGET file itself (``target_rel`` — anti-cheat: the agent
        must reconstruct it from docs, never copy ground truth).
        """
        if not self.repo_root:
            return 0
        ext = ".java" if self.language == "java" else ".py"
        root = os.path.realpath(self.repo_root)
        copied = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d not in self._SKIP_PARTS and d.lower() not in ("test", "tests")
            ]
            for fn in filenames:
                if not fn.endswith(ext):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root).replace("\\", "/")
                # anti-cheat: never expose the ground-truth target source.
                if self.target_rel and rel == self.target_rel:
                    continue
                dest = os.path.join(workspace, "repo_sources", rel)
                os.makedirs(os.path.dirname(dest) or workspace, exist_ok=True)
                try:
                    shutil.copy(full, dest)
                    copied += 1
                except OSError:
                    pass
        return copied


def _dependency_note(dependency_classpath: str, target_package: str) -> str:
    """Spec-side note about the dependency closure (multi-file repos).

    Tells the agent the rest of the repository is already compiled and on the
    classpath: it should USE those types (``Element`` etc.) rather than
    redefining them. Lists only that they exist — no source is dumped (the
    spec stays docs-only for the TARGET entities). Returns ``""`` when there is
    no closure (single-file / default-package mode).
    """
    if not dependency_classpath and not target_package:
        return ""
    lines = ["## Dependency closure (available on the classpath)"]
    if target_package:
        lines.append(
            f"This file belongs to package `{target_package}`. Keep its "
            f"`package {target_package};` declaration."
        )
    lines.append(
        "Every OTHER class in the repository is already compiled as a "
        "ground-truth dependency and is on `compile_check`'s classpath. "
        "Reference those types directly (import them by their package as "
        "needed); do NOT re-declare or re-implement them here. Only the TARGET "
        "entities listed above are yours to implement."
    )
    return "\n".join(lines) + "\n"


def _agents_md(
    module: Module, target: str, language: str, target_package: str = "",
    has_repo_sources: bool = False,
) -> str:
    """Project-context note injected into the agent's system prompt."""
    entity_lines = "\n".join(
        f"- {q} ({e.kind.value})" for q, e in module.entities.items()
    ) or "- (none listed)"
    package_note = ""
    if target_package:
        package_note = (
            f"Package: `{target_package}` — the target file lives under "
            f"`{os.path.dirname(target)}/` and must keep its "
            f"`package {target_package};` line. Other repo classes are already "
            f"compiled on the classpath; use them, do not re-declare them.\n"
        )
    repo_sources_files = ""
    repo_sources_note = ""
    if has_repo_sources:
        repo_sources_files = (
            "- `repo_sources/` — read-only copies of the rest of the "
            "repository's source (your dependencies). Read these to learn the "
            "REAL APIs.\n"
        )
        repo_sources_note = (
            "\n## Resolving dependency APIs\n"
            "Before you import or call any type from another package, CONFIRM "
            "it against `repo_sources/` instead of guessing. Grep there for the "
            "class to find its exact package, method names, and signatures — "
            "guessing a package (e.g. the wrong sub-package for a helper class) "
            "is the most common cause of a non-compiling reconstruction. "
            "`repo_sources/` does NOT contain the target file itself or any "
            "tests — only your dependencies.\n"
        )
    return (
        f"# Code-generation workspace\n\n"
        f"Module under construction: `{module.name}` ({language}).\n"
        f"Target file: `{target}` — implement EVERY entity below in this one file.\n"
        f"{package_note}\n"
        f"## Entities to implement\n{entity_lines}\n\n"
        f"## Files here\n"
        f"- `spec.md` — the per-entity documentation (your source of truth).\n"
        f"- `{target}` — the implementation you write.\n"
        f"{repo_sources_files}"
        f"- `AGENTS.md` — this note.\n"
        f"{repo_sources_note}\n"
        f"There are NO tests in this workspace and you have no access to the "
        f"grading suite. `compile_check` is your only feedback tool.\n"
    )
