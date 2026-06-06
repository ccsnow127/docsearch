"""Build a search :class:`Module` (and its initial docs) from parsed sources.

The bi-level search operates on the abstract data model in
:mod:`docsearch.search.model`: a :class:`Module` is a set of
:class:`Entity` objects plus an internal ``(caller, callee)`` call graph. This
module is the bridge from the docgen subsystem's structural model
(:class:`docsearch.docgen.models.RepoStructure` / ``FileStructure`` /
``CodeObject``) to that search model.

Two products are derived from a parsed repo:

    * :func:`build_module` maps every ``CodeObject`` to an ``Entity`` (keyed by
      its ``qualified_name``), concatenates file sources into ``Module.source``,
      and populates ``Module.edges`` with internal call edges. Java edges come
      from :func:`docsearch.docgen.java_callgraph.call_edges`; Python edges from
      a small ``ast``-based resolver (``self.m()`` / ``Cls.m()`` / bare
      ``func()``), keeping only edges whose endpoints are both known entities.
    * :func:`build_initial_docs` produces per-entity behavioral prose keyed by
      ``qualified_name``, reusing the docgen :class:`ObjectDocGenerator` so the
      starting docs are exactly the prose docgen already makes.

:func:`build_module_and_docs` is the one-call convenience that parses a path
with the docgen parsers and returns ``(module, initial_docs)``.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Iterable, List, Optional

from docsearch.docgen import java_callgraph, java_parser, python_parser
from docsearch.docgen.models import (
    CodeObject,
    FileStructure,
    OBJ_CLASS,
    OBJ_FUNCTION,
    OBJ_METHOD,
    RepoStructure,
)
from docsearch.docgen.object_doc_generator import ObjectDocGenerator
from docsearch.pipeline.entities import Entity, EntityKind, Module

logger = logging.getLogger(__name__)

__all__ = [
    "build_module",
    "build_initial_docs",
    "build_module_and_docs",
    "build_module_docs_and_repo",
]


# obj_type (OBJ_* constant) -> EntityKind.
_KIND_BY_OBJ_TYPE = {
    OBJ_CLASS: EntityKind.CLASS,
    OBJ_FUNCTION: EntityKind.FUNCTION,
    OBJ_METHOD: EntityKind.METHOD,
}

# Directory names that are never walked (mirrors RepoDocGenerator).
_SKIP_DIRS = {"__pycache__"}

# Extension -> ("language", parser module) dispatch table (mirrors RepoDocGenerator).
_EXT_LANGUAGE = {
    ".py": "python",
    ".java": "java",
}
_PARSERS = {
    "python": python_parser,
    "java": java_parser,
}


# --------------------------------------------------------------------------- #
# Module construction
# --------------------------------------------------------------------------- #
def build_module(repo: RepoStructure, *, language: str) -> Module:
    """Build a search :class:`Module` from a parsed docgen ``repo``.

    Each :class:`CodeObject` becomes an :class:`Entity` keyed by its
    ``qualified_name`` (the same key the docs are keyed by), with its kind
    mapped from ``obj_type``, plus its signature and full source. ``Module.source``
    is the concatenation of all file sources; ``Module.language`` is ``language``.

    Edges are internal-only ``(caller, callee)`` pairs: derived via
    :func:`docsearch.docgen.java_callgraph.call_edges` for Java and via an
    ``ast`` pass for Python. ``Module.add_edge`` already drops any edge whose
    endpoints are not both known entities, so all edges are guaranteed internal.

    Args:
        repo: The parsed repository structure.
        language: ``"java"`` or ``"python"`` (drives both edge extraction and
            ``Module.language``).

    Returns:
        A populated :class:`Module`.
    """
    lang = (language or "python").lower()
    module = Module(name=repo.project_name, language=lang)

    # Pass 1: entities. Overloaded methods / constructors can share a
    # qualified_name; first occurrence wins (matches the docs-keying policy).
    for obj in repo.all_objects():
        if obj.qualified_name in module.entities:
            continue
        module.add_entity(_make_entity(obj))

    module.source = _concat_sources(repo.files)

    # Pass 2: internal call edges.
    qualnames = set(module.entities)
    if lang == "java":
        edges = java_callgraph.call_edges(repo.files, qualnames)
    else:
        edges = _python_call_edges(repo.files, qualnames)
    for caller, callee in edges:
        if caller != callee:
            module.add_edge(caller, callee)  # internal-only by construction

    return module


def _make_entity(obj: CodeObject) -> Entity:
    """Map one :class:`CodeObject` to a search :class:`Entity`."""
    # CodeObject.fields prepends the class-signature line (ends with "{"/":")
    # before the real field declarations; drop it so Entity.fields holds only
    # the declared fields/constants.
    field_lines = tuple(
        f for f in (obj.fields or [])
        if not (f.rstrip().endswith("{") or f.rstrip().endswith(":"))
    )
    return Entity(
        qualname=obj.qualified_name,
        kind=_KIND_BY_OBJ_TYPE.get(obj.obj_type, EntityKind.FUNCTION),
        signature=obj.signature or "",
        source=obj.code or "",
        fields=field_lines,
    )


def _concat_sources(files: Iterable[FileStructure]) -> str:
    """Concatenate file sources into a single reference blob, file-delimited."""
    chunks: List[str] = []
    for fs in files:
        src = fs.source_code or ""
        chunks.append(f"# ===== {fs.file_path} =====\n{src}")
    return "\n\n".join(chunks)


# --------------------------------------------------------------------------- #
# Python call-edge extraction (ast-based; Java is handled by java_callgraph)
# --------------------------------------------------------------------------- #
def _python_call_edges(
    files: Iterable[FileStructure], qualnames: set
) -> set:
    """Extract internal ``(caller, callee)`` edges from parsed Python files.

    Two-pass per file: entities are already known (``qualnames``), so this only
    resolves call sites. Recognised forms (best-effort, internal-only):

        * bare ``foo(...)``           -> top-level ``foo`` if known
        * ``Cls.foo(...)``            -> ``Cls.foo`` if known, else ``Cls``
        * ``self.foo(...)`` in ``Cls`` -> ``Cls.foo`` if known

    Anything else (chained / attribute receivers) is dropped; the search's
    runtime worthy check is the safety net for missed edges. Never raises:
    a file that fails to parse simply yields no edges.
    """
    import ast

    edges: set = set()
    for fs in files:
        if (fs.language or "").lower() != "python":
            continue
        try:
            tree = ast.parse(fs.source_code or "")
        except SyntaxError:
            continue

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _collect_python_calls(
                    node, node.name, None, qualnames, edges
                )
            elif isinstance(node, ast.ClassDef):
                cls = node.name
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        caller = f"{cls}.{item.name}"
                        # Class-body methods belong to the method entity if
                        # known, else to the class entity itself.
                        caller = caller if caller in qualnames else cls
                        _collect_python_calls(item, caller, cls, qualnames, edges)
                    else:
                        # Class-body statements (field initializers, etc.)
                        # are attributed to the class entity.
                        _collect_python_calls(item, cls, cls, qualnames, edges)
    return edges


def _collect_python_calls(
    node, caller: str, cls_context: Optional[str], qualnames: set, edges: set
) -> None:
    """Walk ``node`` and add resolved internal edges for ``caller``."""
    import ast

    if caller not in qualnames:
        return
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        callee = _resolve_python_call(sub.func, cls_context, qualnames)
        if callee and callee != caller:
            edges.add((caller, callee))


def _resolve_python_call(func, cls_context: Optional[str], qualnames: set):
    """Resolve one Python call target to a known qualname, or ``None``."""
    import ast

    if isinstance(func, ast.Name):
        return func.id if func.id in qualnames else None

    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        base = func.value.id
        if base == "self" and cls_context:
            qn = f"{cls_context}.{func.attr}"
            return qn if qn in qualnames else None
        qn = f"{base}.{func.attr}"
        if qn in qualnames:
            return qn
        if base in qualnames:  # call lands on the class entity
            return base
    return None


# --------------------------------------------------------------------------- #
# Initial docs
# --------------------------------------------------------------------------- #
def build_initial_docs(repo: RepoStructure, llm) -> Dict[str, str]:
    """Generate per-entity behavioral prose keyed by ``qualified_name``.

    Reuses the docgen :class:`ObjectDocGenerator` so the starting docs are
    exactly the per-entity prose docgen already produces. Overloaded
    methods/constructors share a ``qualified_name``; the first occurrence wins,
    so each entity gets a single prose entry. A failed prose generation for one
    object is logged and skipped rather than aborting the whole build.

    Args:
        repo: The parsed repository structure.
        llm: An LLM client exposing
            ``generate(prompt, temperature=0, system=None) -> str``.

    Returns:
        ``{qualified_name: prose}``.
    """
    from concurrent.futures import ThreadPoolExecutor

    generator = ObjectDocGenerator(llm)

    # Generate per-MODULE in batched LLM calls (one call per ~10 entities) rather
    # than one call per entity: the full file source is sent once per batch, not
    # once per entity (N x input tokens -> ~ceil(N/10)x). Each call returns a JSON
    # {qualified_name: doc} object; any entity a batch omits is retried and, if
    # still missing, documented individually so none is left empty. The search
    # still refines each entity individually. Files are documented concurrently.
    total = sum(len(fs.objects) for fs in repo.files)
    print(f"Generating initial documentation for {total} entit"
          f"{'y' if total == 1 else 'ies'} (batched per module)...", flush=True)

    docs: Dict[str, str] = {}
    files = list(repo.files)
    max_workers = min(8, max(1, len(files)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for per_file in pool.map(
            lambda fs: _safe_module_docs(generator, fs), files
        ):
            for qn, doc in per_file.items():
                docs.setdefault(qn, doc)
    print(f"  initial docs: {len(docs)}/{total} entities documented", flush=True)
    return docs


def _safe_module_docs(generator, fs) -> Dict[str, str]:
    """generate_module_docs for one file; never abort the whole build."""
    try:
        return generator.generate_module_docs(fs)
    except Exception as exc:
        logger.warning("Module-doc generation failed for %s: %s", fs.module_name, exc)
        return {}


# --------------------------------------------------------------------------- #
# Convenience: path -> (Module, initial_docs)
# --------------------------------------------------------------------------- #
def build_module_and_docs(path: str, llm, language: Optional[str] = None):
    """Parse the repo at ``path`` and return ``(module, initial_docs)``.

    Parses with the docgen language parsers (directory walk or single file),
    builds the search :class:`Module` and the per-entity initial docs.

    Args:
        path: A directory (walked recursively) or a single source file.
        llm: LLM client used to generate the initial per-entity prose.
        language: Optional forced language (``"python"`` / ``"java"``); when
            ``None`` the file extension decides per file and the repo's dominant
            language is used for the module.

    Returns:
        ``(Module, dict[str, str])``.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    module, initial_docs, _repo = build_module_docs_and_repo(path, llm, language)
    return module, initial_docs


def build_module_docs_and_repo(path: str, llm, language: Optional[str] = None):
    """Parse ``path`` and return ``(module, initial_docs, repo)``.

    Same as :func:`build_module_and_docs` but also returns the parsed
    :class:`docsearch.docgen.models.RepoStructure`. Callers that need to
    re-assemble canonical markdown from refined per-entity docs (via
    :class:`docsearch.docgen.doc_assembler.DocAssembler`) need the repo to
    preserve the original structural layout, so this avoids re-parsing.

    Args:
        path: A directory (walked recursively) or a single source file.
        llm: LLM client used to generate the initial per-entity prose.
        language: Optional forced language (``"python"`` / ``"java"``).

    Returns:
        ``(Module, dict[str, str], RepoStructure)``.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    repo = _parse_repo(path, language)
    module = build_module(repo, language=repo.language)
    initial_docs = build_initial_docs(repo, llm)
    return module, initial_docs, repo


# --------------------------------------------------------------------------- #
# Parsing (mirrors RepoDocGenerator's parse stage, without the LLM/assembler)
# --------------------------------------------------------------------------- #
def _parse_repo(path: str, language: Optional[str]) -> RepoStructure:
    """Parse ``path`` into a :class:`RepoStructure` using the docgen parsers."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Path does not exist: {path}")

    forced = language.lower() if language else None
    if os.path.isdir(path):
        project_name = (
            os.path.basename(os.path.abspath(path.rstrip(os.sep))) or "project"
        )
        files = _parse_directory(path, forced)
    else:
        project_name = os.path.splitext(os.path.basename(path))[0] or "project"
        fs = _parse_one_file(path, forced)
        files = [fs] if fs is not None else []

    return RepoStructure(
        project_name=project_name,
        language=_dominant_language(files),
        files=files,
    )


def _is_test_file(filename: str) -> bool:
    """Heuristic: is this a test file (excluded from the module under doc)?

    Tests are not part of the module being documented/reimplemented, and the
    DocSearch phi signal comes from running the (hidden) tests against the
    generated code — so test files must never become source entities.
    """
    stem = os.path.splitext(filename)[0]
    return (
        stem.endswith("Test")          # Java: IndicatorsTest.java
        or stem.startswith("Test")     # Java: TestIndicators.java
        or stem.startswith("test_")    # Python: test_indicators.py
        or stem.endswith("_test")      # Python: indicators_test.py
        or "Tests" in stem             # Java: FooTests.java
    )


def _parse_directory(root: str, forced: Optional[str]) -> List[FileStructure]:
    """Walk ``root`` and parse every supported, non-hidden, non-test source file."""
    files: List[FileStructure] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".")
            and d not in _SKIP_DIRS
            and d.lower() not in ("test", "tests")
        ]
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext not in _EXT_LANGUAGE:
                continue
            if _is_test_file(filename):
                continue
            fs = _parse_one_file(os.path.join(dirpath, filename), forced)
            if fs is not None:
                files.append(fs)
    files.sort(key=lambda f: f.file_path)
    return files


def _parse_one_file(path: str, forced: Optional[str]) -> Optional[FileStructure]:
    """Read and parse a single file, returning ``None`` on any failure."""
    ext = os.path.splitext(path)[1].lower()
    lang = forced or _EXT_LANGUAGE.get(ext)
    parser = _PARSERS.get(lang)
    if parser is None:
        logger.warning("Skipping unsupported file (no parser): %s", path)
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            source_code = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Skipping unreadable file %s: %s", path, exc)
        return None
    try:
        return parser.parse_file(path, source_code)
    except Exception as exc:  # never abort the run for one bad file
        logger.warning("Skipping file that failed to parse %s: %s", path, exc)
        return None


def _dominant_language(files: List[FileStructure]) -> str:
    """Return the most common file language, defaulting to ``"python"``."""
    counts: Dict[str, int] = {}
    for fs in files:
        counts[fs.language] = counts.get(fs.language, 0) + 1
    if not counts:
        return "python"
    return max(counts, key=counts.get)
