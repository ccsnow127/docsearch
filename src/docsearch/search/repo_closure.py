"""Repo dependency closure: compile a whole repository from ground truth once,
so a single target file can be reimplemented / tested against the *rest* of the
repo as a fixed dependency context.

This is the contract that unlocks multi-file repos (e.g. jsoup) for the
per-file DocSearch loop. The unit of optimization is ONE source file; every
other file in the repo is the ground-truth dependency closure. At each
evaluation only the target file is recompiled (the generated version), and its
``.class`` output is placed FIRST on the classpath so it shadows the
ground-truth version while all dependencies resolve against the closure.

Build strategy (Java):
  * If the repo has a ``pom.xml``: ``mvn -q compile`` produces the ground-truth
    classes, and ``mvn dependency:build-classpath`` resolves external jars.
  * Otherwise: ``javac`` all sources into a build dir (no external deps).
Python repos need no compilation — the closure is just the repo roots on
``PYTHONPATH``.

The builder is implemented in this module; consumers (JavaTestExecutor,
AgentCodeGenerator, the Java test generator) take ``deps_classpath`` /
``classpath_for_eval`` and never re-derive it.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# A repo is compiled/parsed at most once per process. Keyed by the realpath of
# the repo root so distinct relative spellings of the same directory share one
# RepoClosure.
_CLOSURE_CACHE: Dict[str, "RepoClosure"] = {}


@dataclass
class RepoClosure:
    """The ground-truth dependency context for one repository.

    Attributes:
        repo_root: Absolute path to the repository root.
        language: "java" | "python".
        build_system: "maven" | "javac" | "python".
        classes_dir: Directory of ground-truth compiled ``.class`` files
            (Java). Empty for Python.
        deps_classpath: Colon-joined classpath = ``classes_dir`` + resolved
            external dependency jars (Java). JUnit jars are appended by the
            executor, not here. Empty for Python.
        pythonpath: Colon-joined import roots (Python). Empty for Java.
        source_files: Repo-relative paths of all (non-test) source files.
        file_for_qualname: Map entity qualified-name -> repo-relative source
            file that defines it (used to scope per-file optimization).
    """

    repo_root: str
    language: str
    build_system: str
    classes_dir: str = ""
    deps_classpath: str = ""
    pythonpath: str = ""
    source_files: Tuple[str, ...] = ()
    file_for_qualname: Dict[str, str] = field(default_factory=dict)

    def classpath_for_eval(self, generated_build_dir: str, extra: str = "") -> str:
        """Classpath for compiling/running a generated target against the closure.

        ``generated_build_dir`` (the freshly compiled generated target +
        its tests) goes FIRST so its classes shadow the ground-truth ones in
        ``classes_dir``; then the closure deps; then any ``extra`` (e.g. JUnit).
        """
        parts = [generated_build_dir]
        if self.deps_classpath:
            parts.append(self.deps_classpath)
        if extra:
            parts.append(extra)
        return os.pathsep.join(p for p in parts if p)

    def qualnames_in_file(self, rel_path: str) -> list[str]:
        """The entity qualified-names defined in ``rel_path`` (the target file)."""
        return [q for q, f in self.file_for_qualname.items() if f == rel_path]


def build_closure(
    repo_root: str,
    language: str,
    repo_structure: Optional[object] = None,
) -> RepoClosure:
    """Build (and compile, for Java) the dependency closure for a repo.

    Args:
        repo_root: Path to the repository root.
        language: "java" | "python".
        repo_structure: Optional pre-parsed
            :class:`docsearch.docgen.models.RepoStructure`; if provided, its
            entities populate ``file_for_qualname`` without re-parsing.

    Returns:
        A populated :class:`RepoClosure`.

    Implementation note (filled in by the closure builder):
        Java: detect ``pom.xml`` -> Maven compile + dependency classpath;
        else javac all sources. Cache the compiled output under the repo so a
        repo is built at most once per process. Python: collect import roots.
    """
    key = os.path.realpath(repo_root)
    cached = _CLOSURE_CACHE.get(key)
    if cached is not None:
        return cached

    # Use the ABSOLUTE repo root so every derived path (classes_dir,
    # deps_classpath, pythonpath) is absolute. These end up on a javac/java
    # classpath that is run with cwd=<temp build dir>; a relative
    # "<repo>/target/classes" would resolve at compile time (cwd=repo) but NOT
    # at runtime (cwd=build dir), causing NoClassDefFoundError for the repo's
    # own classes. Absolute paths resolve regardless of cwd.
    repo_root = key

    lang = (language or "").lower()
    if lang == "python":
        closure = _build_python_closure(repo_root, repo_structure)
    elif lang == "java":
        closure = _build_java_closure(repo_root, repo_structure)
    else:
        raise ValueError(
            f"Unsupported language: {language!r}. Expected 'java' or 'python'."
        )

    _CLOSURE_CACHE[key] = closure
    return closure


# --------------------------------------------------------------------------- #
# Source-file discovery
# --------------------------------------------------------------------------- #
# Directory names that are never part of a source closure.
_SKIP_DIRS = {
    "__pycache__", ".git", ".hg", ".svn", "target", "build", "out",
    "node_modules", ".idea", ".mvn", ".gradle", "bin",
}


def _is_test_path(rel_path: str) -> bool:
    """Whether a repo-relative path is a test source (excluded from the closure).

    Skips anything under a ``src/test`` directory and any file whose basename
    matches the JUnit-style ``*Test.java`` / ``Test*.java`` conventions.
    """
    norm = rel_path.replace("\\", "/")
    parts = norm.split("/")
    if "test" in parts or "tests" in parts:
        return True
    if "src/test" in norm:
        return True
    base = parts[-1]
    stem = base[:-5] if base.endswith(".java") else base
    if stem.endswith("Test") or stem.startswith("Test"):
        return True
    return False


def _collect_source_files(repo_root: str, ext: str) -> List[str]:
    """Repo-relative paths of all non-test ``ext`` files under ``repo_root``."""
    found: List[str] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d not in _SKIP_DIRS
        ]
        for filename in filenames:
            if not filename.endswith(ext):
                continue
            full = os.path.join(dirpath, filename)
            rel = os.path.relpath(full, repo_root).replace("\\", "/")
            if _is_test_path(rel):
                continue
            found.append(rel)
    found.sort()
    return found


# --------------------------------------------------------------------------- #
# file_for_qualname construction
# --------------------------------------------------------------------------- #
def _map_from_repo_structure(repo_structure: object, repo_root: str) -> Dict[str, str]:
    """Build qualified_name -> repo-relative path from a pre-parsed RepoStructure."""
    mapping: Dict[str, str] = {}
    files = getattr(repo_structure, "files", None) or []
    for file_struct in files:
        rel = _to_repo_relative(getattr(file_struct, "file_path", ""), repo_root)
        if not rel:
            continue
        for obj in getattr(file_struct, "objects", None) or []:
            qn = getattr(obj, "qualified_name", None)
            if qn:
                mapping.setdefault(qn, rel)
    return mapping


def _to_repo_relative(file_path: str, repo_root: str) -> str:
    """Normalize a (possibly absolute) file path to a repo-relative POSIX path."""
    if not file_path:
        return ""
    if os.path.isabs(file_path):
        try:
            file_path = os.path.relpath(file_path, repo_root)
        except ValueError:
            return ""
    return file_path.replace("\\", "/")


def _map_by_parsing(repo_root: str, rel_files: List[str], parser) -> Dict[str, str]:
    """Parse each source file and map its qualified-names to its repo-relative path.

    A single unparseable/unreadable file is logged and skipped; it never aborts
    the closure build.
    """
    mapping: Dict[str, str] = {}
    for rel in rel_files:
        full = os.path.join(repo_root, rel)
        try:
            with open(full, "r", encoding="utf-8") as handle:
                source_code = handle.read()
            structure = parser.parse_file(rel, source_code)
        except Exception as exc:  # never abort the closure for one bad file
            logger.warning("Skipping file that failed to parse %s: %s", rel, exc)
            continue
        for obj in structure.objects:
            mapping.setdefault(obj.qualified_name, rel)
    return mapping


# --------------------------------------------------------------------------- #
# Python
# --------------------------------------------------------------------------- #
def _python_roots(repo_root: str) -> List[str]:
    """Import roots for a Python repo.

    A directory is an import root if it (directly) contains a top-level package
    (a sub-directory with ``__init__.py``) or a top-level module while not
    itself being a package. Falls back to ``repo_root`` when nothing is found.
    """
    roots: List[str] = []
    seen = set()

    def _add(path: str) -> None:
        real = os.path.realpath(path)
        if real not in seen:
            seen.add(real)
            roots.append(path)

    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d not in _SKIP_DIRS
        ]
        # The parent of a top-level package (one not itself inside a package)
        # is an import root.
        if "__init__.py" in filenames:
            parent = os.path.dirname(dirpath)
            if not os.path.exists(os.path.join(parent, "__init__.py")):
                _add(parent)
            # Do not descend into the package's own sub-packages for root
            # detection; their parents are inside the package.
            dirnames[:] = []

    if not roots:
        _add(repo_root)
    return roots


def _build_python_closure(
    repo_root: str, repo_structure: Optional[object]
) -> RepoClosure:
    from docsearch.docgen import python_parser

    rel_files = _collect_source_files(repo_root, ".py")
    if repo_structure is not None:
        file_for_qualname = _map_from_repo_structure(repo_structure, repo_root)
    else:
        file_for_qualname = _map_by_parsing(repo_root, rel_files, python_parser)

    roots = _python_roots(repo_root)
    return RepoClosure(
        repo_root=repo_root,
        language="python",
        build_system="python",
        classes_dir="",
        deps_classpath="",
        pythonpath=os.pathsep.join(roots),
        source_files=tuple(rel_files),
        file_for_qualname=file_for_qualname,
    )


# --------------------------------------------------------------------------- #
# Java
# --------------------------------------------------------------------------- #
def _build_java_closure(
    repo_root: str, repo_structure: Optional[object]
) -> RepoClosure:
    from docsearch.docgen import java_parser

    rel_files = _collect_source_files(repo_root, ".java")
    if repo_structure is not None:
        file_for_qualname = _map_from_repo_structure(repo_structure, repo_root)
    else:
        file_for_qualname = _map_by_parsing(repo_root, rel_files, java_parser)

    pom = os.path.join(repo_root, "pom.xml")
    classes_dir = ""
    deps_classpath = ""
    build_system = "javac"

    if os.path.exists(pom):
        maven = _try_maven_build(repo_root)
        if maven is not None:
            classes_dir, deps_classpath = maven
            build_system = "maven"
        else:
            logger.warning(
                "Maven build failed for %s; falling back to javac.", repo_root
            )

    if build_system == "javac":
        classes_dir = _javac_build(repo_root, rel_files)
        deps_classpath = classes_dir

    return RepoClosure(
        repo_root=repo_root,
        language="java",
        build_system=build_system,
        classes_dir=classes_dir,
        deps_classpath=deps_classpath,
        pythonpath="",
        source_files=tuple(rel_files),
        file_for_qualname=file_for_qualname,
    )


def _try_maven_build(repo_root: str) -> Optional[Tuple[str, str]]:
    """Compile with Maven and resolve the dependency classpath.

    Returns ``(classes_dir, deps_classpath)`` on success, or ``None`` if any
    Maven invocation fails (caller falls back to javac). The ground-truth
    classes land in ``<repo_root>/target/classes``; the resolved external
    dependency classpath is written by ``dependency:build-classpath`` to a
    temp file and read back. ``deps_classpath`` is ``target/classes`` followed
    by those external jars.
    """
    target_classes = os.path.join(repo_root, "target", "classes")

    try:
        compile_proc = subprocess.run(
            ["mvn", "-q", "-DskipTests", "compile"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("mvn compile errored in %s: %s", repo_root, exc)
        return None

    if compile_proc.returncode != 0 or not os.path.isdir(target_classes):
        logger.warning(
            "mvn compile failed in %s (rc=%s): %s",
            repo_root, compile_proc.returncode, compile_proc.stderr[-2000:],
        )
        return None

    deps_classpath = target_classes
    cp_fd, cp_file = tempfile.mkstemp(prefix="mvn_cp_", suffix=".txt")
    os.close(cp_fd)
    try:
        cp_proc = subprocess.run(
            [
                "mvn", "-q", "dependency:build-classpath",
                f"-Dmdep.outputFile={cp_file}",
                # Compile scope: include compile + provided deps (e.g. jspecify
                # for @Nullable, needed to compile the sources) but EXCLUDE
                # test-scope deps (the repo's own JUnit), which otherwise clash
                # with our libs/ JUnit and break the platform launcher/engine.
                "-DincludeScope=compile",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if cp_proc.returncode == 0:
            try:
                with open(cp_file, "r", encoding="utf-8") as handle:
                    external = handle.read().strip()
            except OSError as exc:
                logger.warning("Could not read maven classpath file: %s", exc)
                external = ""
            if external:
                deps_classpath = os.pathsep.join([target_classes, external])
        else:
            logger.warning(
                "mvn dependency:build-classpath failed in %s (rc=%s): %s",
                repo_root, cp_proc.returncode, cp_proc.stderr[-2000:],
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("mvn dependency:build-classpath errored in %s: %s", repo_root, exc)
    finally:
        try:
            os.remove(cp_file)
        except OSError:
            pass

    return target_classes, deps_classpath


def _javac_build(repo_root: str, rel_files: List[str]) -> str:
    """Compile all non-test sources into a fresh build dir; return that dir.

    Uses ``-source 17 -target 17`` and ``-d <build_dir>``. The build dir is the
    closure's ``classes_dir`` and also its ``deps_classpath`` (no external
    dependency resolution in the javac path). Compilation errors are logged but
    never raised; whatever classes javac managed to emit remain usable.
    """
    build_dir = tempfile.mkdtemp(prefix="closure_javac_")
    if not rel_files:
        return build_dir

    abs_files = [os.path.join(repo_root, rel) for rel in rel_files]
    cmd = ["javac", "-source", "17", "-target", "17", "-d", build_dir] + abs_files
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode != 0:
            logger.warning(
                "javac reported errors building closure for %s: %s",
                repo_root, proc.stderr[-2000:],
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("javac errored building closure for %s: %s", repo_root, exc)
    return build_dir
