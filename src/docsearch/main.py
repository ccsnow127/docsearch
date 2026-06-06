"""
Main entry point for DocSearch: Bilevel tree search for specification optimization.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from docsearch.llm.agent_adapter import make_agent_llm
from .test_executor import TestExecutor
from .java_test_executor import JavaTestExecutor

from .config import DEFAULT_BUDGET, W

from .docgen.doc_assembler import DocAssembler
from .docgen.models import RepoStructure
from .search.codegen_agent import AgentCodeGenerator
from .search.evaluator import JavaEvaluator, PythonEvaluator
from .search.loop import InnerConfig, SearchConfig, run_search
from .search.module_builder import build_module_docs_and_repo
from .search.repo_closure import build_closure


def load_module_data(module_name: str, dataset_root: str = None, test_file: str = None, language: str = "python", baseline_doc: str = None) -> dict:
    """Load data for a module from the dataset.

    Supports two input modes:
      1. File path: --module dataset/python/stocktrends/indicators.py
         Auto-detects dataset root (parent of parent), docs, and tests.
      2. Module name + dataset root: --module stocktrends --dataset-root dataset/python

    Args:
        module_name: Module name or path to source file
        dataset_root: Path to dataset root directory (auto-detected if module_name is a file)
        test_file: Optional custom test file path
        language: "python" or "java"
        baseline_doc: Optional path to baseline doc (overrides auto-detection)
    """
    source_path = Path(module_name)

    # Mode 0: module_name is a repository DIRECTORY
    if source_path.exists() and source_path.is_dir():
        return _load_repo_data(source_path, test_file, language, baseline_doc)

    # Mode 1: module_name is a file path
    if source_path.exists() and source_path.is_file():
        source_code = source_path.read_text()
        package_dir = source_path.parent           # e.g., dataset/python/stocktrends
        base_path = package_dir.parent             # e.g., dataset/python
        pkg_name = package_dir.name                # e.g., stocktrends

        # For Python, target_module = "package.module" (e.g., stocktrends.indicators)
        if language == "python":
            target_module = f"{pkg_name}.{source_path.stem}"
        else:
            target_module = pkg_name

        # Find base doc
        if baseline_doc:
            base_doc_path = Path(baseline_doc)
        elif language == "java":
            base_doc_path = base_path / "docs" / "baseline_doc_java.md"
            if not base_doc_path.exists():
                base_doc_path = base_path / "docs" / "baseline_doc.md"
        else:
            base_doc_path = base_path / "docs" / "baseline_doc.md"

        if not base_doc_path.exists():
            # Auto-generate baseline doc via the unified repo-level path.
            base_doc = _auto_generate_baseline_from_path(str(source_path), language)
            base_doc_path.parent.mkdir(parents=True, exist_ok=True)
            base_doc_path.write_text(base_doc)
            print(f"Auto-generated baseline doc: {base_doc_path}")
        else:
            base_doc = base_doc_path.read_text()

        # Extract entities
        entities = extract_entities(base_doc)

        # Find test file
        if test_file:
            test_path = Path(test_file)
        else:
            test_path = _find_test_file(base_path, pkg_name, language)

        return {
            "base_doc": base_doc,
            "source_code": source_code,
            "entities": entities,
            "test_path": str(test_path),
            "module_path": str(base_path),
            "target_module": target_module,
            "language": language,
        }

    # Mode 2: module_name is a module name, requires dataset_root
    if dataset_root is None:
        raise ValueError(
            f"'{module_name}' is not a file path. "
            "Please provide --dataset-root or pass a source file path to --module."
        )

    dataset_root_path = Path(dataset_root)
    module_path = dataset_root_path / module_name

    # Determine base path: use module_path if it has docs/, else dataset_root
    if (module_path / "docs").exists():
        base_path = module_path
    else:
        base_path = dataset_root_path

    # Load base documentation
    if baseline_doc:
        base_doc_path = Path(baseline_doc)
    elif language == "java":
        base_doc_path = base_path / "docs" / "baseline_doc_java.md"
        if not base_doc_path.exists():
            base_doc_path = base_path / "docs" / "baseline_doc.md"
    else:
        base_doc_path = base_path / "docs" / "baseline_doc.md"

    # Load source code first (needed for potential auto-generation)
    if language == "java":
        source_code = _find_java_source(module_path, base_path, module_name)
    else:
        source_code = _find_python_source(module_path, base_path, module_name)

    if not base_doc_path.exists():
        # Auto-generate baseline doc via the unified repo-level path.
        base_doc = _auto_generate_baseline(source_code, language, name=module_name)
        base_doc_path.parent.mkdir(parents=True, exist_ok=True)
        base_doc_path.write_text(base_doc)
        print(f"Auto-generated baseline doc: {base_doc_path}")
    else:
        base_doc = base_doc_path.read_text()

    entities = extract_entities(base_doc)

    if test_file:
        test_path = Path(test_file)
    else:
        test_path = _find_test_file(base_path, module_name, language)
        if test_path is None:
            test_path = _find_test_file(module_path, module_name, language)

    if test_path is None:
        raise FileNotFoundError(f"Test file not found under {base_path} or {module_path}")

    target_module = module_name

    return {
        "base_doc": base_doc,
        "source_code": source_code,
        "entities": entities,
        "test_path": str(test_path),
        "module_path": str(base_path),
        "target_module": target_module,
        "language": language,
    }


def _detect_directory_language(repo_path: Path) -> str:
    """Detect the dominant language of a repo directory (.java vs .py)."""
    py = sum(1 for _ in repo_path.glob("**/*.py"))
    java = sum(1 for _ in repo_path.glob("**/*.java"))
    return "java" if java > py else "python"


def _read_repo_source(repo_path: Path, language: str) -> str:
    """Concatenate all non-test source files of ``language`` under ``repo_path``."""
    ext = ".java" if language == "java" else ".py"
    files = sorted(
        f for f in repo_path.glob(f"**/*{ext}")
        if f.name != "__init__.py"
        and "test" not in f.name.lower()
        and "__pycache__" not in f.parts
    )
    parts = [f"# === {f.relative_to(repo_path)} ===\n{f.read_text()}" for f in files]
    return "\n\n".join(parts)


def _load_repo_data(repo_path: Path, test_file: str, language: str, baseline_doc: str) -> dict:
    """Load data for a repository DIRECTORY passed as --module.

    Treats the directory as a one-or-more-file repo: builds (or loads) the
    baseline doc via the unified repo-level path, gathers source for the
    searcher, and locates a test file.
    """
    # Detect the dominant language unless the caller forced a non-default one.
    if language == "python":
        language = _detect_directory_language(repo_path)

    repo_name = repo_path.name

    # Locate the baseline doc (override > docs/ dir > auto-generate).
    if baseline_doc:
        base_doc_path = Path(baseline_doc)
    elif language == "java":
        base_doc_path = repo_path / "docs" / "baseline_doc_java.md"
        if not base_doc_path.exists():
            base_doc_path = repo_path / "docs" / "baseline_doc.md"
    else:
        base_doc_path = repo_path / "docs" / "baseline_doc.md"

    if not base_doc_path.exists():
        base_doc = _auto_generate_baseline_from_path(str(repo_path), language)
        base_doc_path.parent.mkdir(parents=True, exist_ok=True)
        base_doc_path.write_text(base_doc)
        print(f"Auto-generated baseline doc: {base_doc_path}")
    else:
        base_doc = base_doc_path.read_text()

    entities = extract_entities(base_doc)

    source_code = _read_repo_source(repo_path, language)

    if test_file:
        test_path = Path(test_file)
    else:
        test_path = _find_test_file(repo_path, repo_name, language)
    if test_path is None:
        raise FileNotFoundError(f"Test file not found under {repo_path}")

    return {
        "base_doc": base_doc,
        "source_code": source_code,
        "entities": entities,
        "test_path": str(test_path),
        "module_path": str(repo_path),
        "target_module": repo_name,
        "language": language,
    }


def _find_test_file(base_path: Path, module_name: str, language: str) -> Path:
    """Find test file under base_path."""
    if language == "java":
        candidates = [
            base_path / "tests" / "TestIndicatorsJava.java",
            base_path / "tests" / "TestIndicators.java",
            base_path / "tests" / f"Test{module_name.capitalize()}.java",
            base_path / "repo_test" / f"Test{module_name.capitalize()}.java",
        ]
    else:
        candidates = [
            base_path / "tests" / f"test_{module_name}.py",
            base_path / "tests" / "test_indicators.py",
            base_path / "repo_test" / f"test_{module_name}.py",
        ]
    for loc in candidates:
        if loc.exists():
            return loc
    return None


def _find_java_source(module_path: Path, base_path: Path, module_name: str) -> str:
    """Find Java source code."""
    candidates = [
        module_path / "java" / "indicators.java",
        module_path / f"{module_name}_java" / "indicators.java",
        base_path / module_name / "indicators.java",
    ]
    for p in candidates:
        if p.exists():
            return p.read_text()

    # Fallback glob (exclude test files)
    search = module_path if module_path.exists() else base_path
    java_files = [f for f in search.glob("**/*.java")
                  if "test" not in f.name.lower() and "Test" not in f.name]
    if java_files:
        return java_files[0].read_text()

    raise FileNotFoundError(f"Java source not found in: {search}")


def _find_python_source(module_path: Path, base_path: Path, module_name: str) -> str:
    """Find Python source code."""
    # Single file
    single = module_path / f"{module_name}.py"
    if single.exists():
        return single.read_text()

    # Sub-package
    pkg = module_path / module_name
    if pkg.exists() and pkg.is_dir():
        return _read_python_package(pkg)

    # module_path itself is the package
    if module_path.exists() and (module_path / "__init__.py").exists():
        return _read_python_package(module_path)

    # Flat layout
    flat = base_path / module_name
    if flat.exists() and flat.is_dir() and flat != module_path:
        return _read_python_package(flat)

    raise FileNotFoundError(f"Python source not found: {single} or {pkg}")


def _auto_generate_baseline(source_code: str, language: str, name: str = "module") -> str:
    """Auto-generate baseline doc from in-memory source code using default LLM."""
    from .baseline_generator import BaselineDocGenerator

    print("Baseline doc not found — auto-generating from source code...")
    llm = make_agent_llm("gpt-5.2-us")
    generator = BaselineDocGenerator(llm)
    return generator.generate(source_code, language, name=name)


def _auto_generate_baseline_from_path(path: str, language: str = None) -> str:
    """Auto-generate baseline doc from a repo directory or single file path."""
    from .baseline_generator import BaselineDocGenerator

    print("Baseline doc not found — auto-generating from source path...")
    llm = make_agent_llm("gpt-5.2-us")
    generator = BaselineDocGenerator(llm)
    return generator.generate_from_path(path, language)


def _read_python_package(pkg_path: Path) -> str:
    """Read all .py files from a Python package."""
    py_files = sorted([f for f in pkg_path.glob("*.py") if f.name != "__init__.py"])
    if not py_files:
        raise FileNotFoundError(f"No Python files in: {pkg_path}")
    parts = [f"# === {f.name} ===\n{f.read_text()}" for f in py_files]
    return "\n\n".join(parts)


def extract_entities(doc: str) -> list[str]:
    """Extract entity names from documentation."""
    seen = set()
    entities = []

    def _add(name: str):
        if name not in seen:
            seen.add(name)
            entities.append(name)

    # Find ## Function: name
    for match in re.finditer(r'## Function: (\w+)', doc):
        _add(match.group(1))

    # Find ## Class: name
    for match in re.finditer(r'## Class: (\w+)', doc):
        _add(match.group(1))

    # Find ### Method: Class.method (only dot-qualified names like PnF.getState)
    for match in re.finditer(r'### Method: ([\w.]+)', doc):
        name = match.group(1)
        if '.' in name:
            _add(name)

    return entities



def _generate_baseline(args):
    """Generate baseline doc from a source file or repo directory and exit."""
    from .baseline_generator import BaselineDocGenerator

    source_path = Path(args.module)
    if not source_path.exists():
        print(f"Error: source path not found: {args.module}")
        sys.exit(1)

    language = args.language

    print(f"Generating baseline doc from: {args.module} (language: {language})")

    llm = make_agent_llm(args.hint_model)
    generator = BaselineDocGenerator(llm)
    # Unified entry: file OR directory both go through the repo-level path.
    baseline_doc = generator.generate_from_path(str(source_path), language)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(baseline_doc)
        print(f"Baseline doc saved to: {output_path}")
    else:
        print(baseline_doc)


def _assemble_final_doc(repo, docs: dict, language: str, llm=None) -> str:
    """Re-assemble canonical baseline markdown from refined per-entity docs.

    Maps the search's per-entity prose (keyed by ``qualified_name``) back onto
    the parsed :class:`RepoStructure` via :class:`DocAssembler`, so the output
    matches the canonical baseline-doc format exactly as before. When ``llm`` is
    provided, an informative per-module overview is generated so each
    ``## Module:`` section is a real summary, consistent with the detailed
    entity docs (rather than a placeholder).
    """
    module_descriptions = None
    if llm is not None:
        from .docgen.object_doc_generator import ObjectDocGenerator
        gen = ObjectDocGenerator(llm)
        module_descriptions = {}
        for file in getattr(repo, "files", []):
            try:
                module_descriptions[file.module_name] = gen.generate_module_overview(file)
            except Exception:
                pass
    return DocAssembler().assemble(repo, docs, module_descriptions)


def _make_artifact_saver(output_dir: Path, language: str = "python"):
    """Build an ``on_step(node, event)`` callback that persists search artifacts.

    Mirrors the old artifact layout closely enough to be useful:
      <output_dir>/nodes/<node_id>/{info.json, doc.md, code.<ext>, errors.txt}
      <output_dir>/summary.json   (running best phi + per-entity phi)
      <output_dir>/tree.txt        (parent/child structure with phi)
    """
    nodes_dir = output_dir / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)

    def _mean_phi(node) -> float:
        if not node.phi:
            return 0.0
        return sum(node.phi.values()) / len(node.phi)

    def on_step(node, event: str) -> None:
        # 1) Per-node directory.
        node_dir = nodes_dir / f"node_{node.id}"
        node_dir.mkdir(parents=True, exist_ok=True)

        info = {
            "id": node.id,
            "event": event,
            "parent_id": node.parent.id if node.parent is not None else None,
            "refined_entity": node.refined_entity,
            "phi": node.phi,
            "mean_phi": _mean_phi(node),
            "intractable": sorted(node.intractable),
            "depth": node.depth(),
        }
        with open(node_dir / "info.json", "w") as f:
            json.dump(info, f, indent=2)

        # Full assembled doc map (per-entity) for this node.
        with open(node_dir / "docs.json", "w") as f:
            json.dump(node.docs, f, indent=2)

        # Extension follows the RUN's language (not a content guess, which
        # mislabels empty/failed reconstructions as .py on a Java run).
        code_ext = ".java" if language == "java" else ".py"
        (node_dir / f"code{code_ext}").write_text(node.code or "")

        errors = []
        for entity, msgs in node.failures.items():
            for msg in msgs:
                errors.append(f"[{entity}] {msg}")
        (node_dir / "errors.txt").write_text("\n".join(errors))

        # 2) Running summary.
        summary = {
            "event": event,
            "current_node_id": node.id,
            "mean_phi": _mean_phi(node),
            "phi": node.phi,
            "intractable": sorted(node.intractable),
        }
        with open(output_dir / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        # 3) Tree view (walk from this node to root, print ancestry).
        lines = []
        for n in node.path_to_root():
            marker = f"node_{n.id}"
            ent = f" refined={n.refined_entity}" if n.refined_entity else ""
            lines.append(f"{'  ' * n.depth()}{marker} (phi={_mean_phi(n):.3f}){ent}")
        (output_dir / "tree.txt").write_text("\n".join(lines) + "\n")

    return on_step


def _save_run_backup(output_dir, *, final_doc: str, result_meta: dict) -> None:
    """Persist a self-contained backup of a COMPLETED run under ``output_dir``.

    Writes the final product output (``refined_doc.md``) plus a ``result.json``
    capturing the run's status and metrics — including ``budget_fully_used`` so
    a full-budget run is durably recorded as proof the pipeline works end to end.
    No-op when artifacts are disabled (``output_dir is None``).
    """
    if output_dir is None:
        return
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # The DOC (product) stays at the top level; the run METADATA goes under
    # artifacts/ so docs and trajectory/process data are cleanly separated.
    (output_dir / "refined_doc.md").write_text(final_doc)
    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    with open(artifacts_dir / "result.json", "w") as f:
        json.dump(result_meta, f, indent=2)
    print(
        f"Run backup saved to: {output_dir} "
        f"(top-level refined_doc.md; artifacts/result.json, "
        f"status={result_meta.get('status')})"
    )


def _record_testgen(file_output_dir, rel: str, *, status: str, **fields) -> None:
    """Record the per-file test-generation outcome (``testgen.json``) as soon as
    it is known — so the generated suite / skip reason is captured before the
    (long) search, independent of whether the search runs. No-op without artifacts."""
    if file_output_dir is None:
        return
    file_output_dir = Path(file_output_dir)
    file_output_dir.mkdir(parents=True, exist_ok=True)
    record = {"status": status, "file": rel, **fields}
    with open(file_output_dir / "testgen.json", "w") as f:
        json.dump(record, f, indent=2)


# --------------------------------------------------------------------------- #
# Repo mode: optimize a real multi-file repo file-by-file against a closure.
# --------------------------------------------------------------------------- #
_JAVA_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)


def _java_package_of(source_path: Path) -> str:
    """The Java ``package ...;`` declared in ``source_path`` ("" if none/Python)."""
    if source_path.suffix != ".java":
        return ""
    try:
        text = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    m = _JAVA_PACKAGE_RE.search(text)
    return m.group(1) if m else ""


def _untestable_java_reason(target_path: Path) -> "str | None":
    """Return a reason string if a Java file has no testable concrete behavior
    (so test generation would only grind for minutes and then fail), else None.

    Untestable shapes — there is no instantiable code path to assert on:

      * an **annotation type** (``@interface``): no executable code at all;
      * a top-level **interface with no ``default``/``static`` method bodies**:
        every method is abstract, so the behavior lives only in implementors.

    Abstract classes are deliberately NOT treated as untestable: their behavior
    is often reachable through concrete (sometimes nested) subclasses, so they
    still go through the normal test-generation path. The check is conservative
    — it only fires on the FIRST (top-level) declared type, and a comment strip
    avoids matching the keywords inside comments. When unsure it returns None
    and the normal path runs.
    """
    try:
        src = target_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Strip comments so keywords inside them don't trigger a false positive.
    code = re.sub(r"//[^\n]*", " ", re.sub(r"/\*.*?\*/", " ", src, flags=re.S))
    # Find the FIRST top-level type declaration (annotation OR class/interface/
    # enum/record), so a nested type inside a normal class never misleads us.
    m = re.search(r"(@interface\s+\w+)|\b(class|interface|enum|record)\s+\w+", code)
    if not m:
        return None
    if m.group(1):  # @interface <Name>
        return "annotation type (no executable code)"
    if m.group(2) == "interface":
        # An interface is testable only via default/static method bodies.
        has_body = re.search(r"\b(default|static)\b[^=;{}]*\([^;{}]*\)\s*\{", code)
        if not has_body:
            return "pure interface (no default/static method bodies)"
    return None


def run_repo(args, hint_llm, code_llm, search_llm, repo_root: Path, output_dir):
    """Optimize a multi-file repo file-by-file against a fixed ground-truth closure.

    The closure (every OTHER repo file, compiled once) is the dependency context;
    each target source file F is the unit of optimization. For F we generate a
    test suite against the ground-truth closure, build a search ``Module`` scoped
    to F's entities, run the bi-level search with the closure threaded into the
    evaluator + code-gen, and collect F's refined per-entity docs. All files'
    refined docs are aggregated into one canonical repo document via
    :class:`DocAssembler` and written to ``-o``.

    Args:
        args: Parsed CLI args (uses ``--target-file``, ``--max-files``,
            ``--budget``, ``--width``, ``--save-artifacts``, ``-o``, etc.).
        hint_llm / code_llm / search_llm: Pre-built LLM clients / SearchLLM.
        repo_root: The repository directory passed as ``--module``.
        output_dir: Artifact dir (when ``--save-artifacts``) or ``None``.
    """
    from docsearch.testgen.react import TestGeneratorConfig
    from docsearch.testgen.react.react_loop import ReactTestGenerator

    language = args.language

    # a) Build the dependency closure ONCE for the whole repo.
    print(f"Building dependency closure for repo: {repo_root} (language: {language})")
    closure = build_closure(str(repo_root), language)
    print(
        f"Closure: build_system={closure.build_system} "
        f"source_files={len(closure.source_files)} "
        f"deps_classpath={'set' if closure.deps_classpath else 'empty'}"
    )

    # Determine which files to optimize. --target-file optimizes just that file;
    # otherwise iterate all non-test source files (capped by --max-files).
    if args.target_file:
        target = Path(args.target_file)
        if not target.is_absolute():
            # Accept either a repo-relative or a cwd-relative path.
            cand = repo_root / args.target_file
            target = cand if cand.exists() else target
        target_rel = os.path.relpath(target.resolve(), repo_root.resolve()).replace("\\", "/")
        if target_rel not in closure.source_files:
            print(
                f"WARNING: --target-file {args.target_file} is not a non-test "
                f"source file in the closure; processing it anyway."
            )
        target_rels = [target_rel]
    else:
        target_rels = list(closure.source_files)
        # Optional sub-path filter: keep only files under --target-dir (still
        # building the closure from the whole repo so deps resolve).
        if args.target_dir:
            prefix = args.target_dir.replace("\\", "/").strip("/")
            filtered = [r for r in target_rels if r.replace("\\", "/").startswith(prefix + "/")
                        or r.replace("\\", "/") == prefix]
            if not filtered:
                print(f"WARNING: --target-dir {args.target_dir} matched no closure source files.")
            target_rels = filtered
        if args.max_files and args.max_files > 0 and len(target_rels) > args.max_files:
            skipped = target_rels[args.max_files:]
            target_rels = target_rels[:args.max_files]
            print(
                f"--max-files={args.max_files}: processing {len(target_rels)} of "
                f"{len(target_rels) + len(skipped)} files; SKIPPING {len(skipped)}: "
                f"{skipped}"
            )

    print(f"Files to process ({len(target_rels)}): {target_rels}")

    # --test-file reuses ONE existing suite; it only makes sense for a single
    # target (otherwise the same test would be wrongly reused for every file).
    if args.test_file and len(target_rels) != 1:
        raise SystemExit(
            "--test-file reuses a single test suite and requires exactly one "
            f"target file (got {len(target_rels)}). Pass --target-file too."
        )

    # Aggregate the per-file refined docs + parsed file structures.
    aggregated_prose: dict = {}
    aggregated_files: list = []
    processed: list[str] = []
    skipped: list[str] = []
    per_file_results: list = []  # per-file metrics for the run backup

    def _document_no_tests(rel, target_path, file_output_dir, safe, reason):
        """Document a file with NO test signal: emit only the baseline doc and
        record a vacuous phi=1.0 (no failing evidence), skipping the search.

        Used both for files that are untestable up front (early-skip) and for
        files where test generation ran but produced no usable tests.
        """
        print(f"NOTE: {rel}: {reason}; documenting with vacuous phi=1.0 "
              f"(no test signal -> baseline doc only, no search).")
        module, initial_docs, repo = build_module_docs_and_repo(
            str(target_path), hint_llm, language=language
        )
        if output_dir is not None and safe is not None:
            try:
                docs_dir = output_dir / "docs"
                docs_dir.mkdir(parents=True, exist_ok=True)
                (docs_dir / f"{safe}.md").write_text(
                    _assemble_final_doc(repo, initial_docs, language, llm=hint_llm)
                )
            except Exception as exc:
                print(f"WARNING: could not write per-file doc for {rel}: {exc}")
        per_file_results.append({
            "file": rel,
            "entities": len(module.entities),
            "best_mean_phi": 1.0,
            "iterations": 0,
            "budget_fully_used": False,
            "intractable": [],
            "no_tests": True,
        })
        _record_testgen(file_output_dir, rel, status="documented_no_tests",
                        reason=reason)
        aggregated_prose.update(initial_docs)
        aggregated_files.extend(repo.files)
        processed.append(rel)

    for rel in target_rels:
        target_path = repo_root / rel
        print("\n" + "=" * 60)
        print(f"Target file: {rel}")
        print("=" * 60)

        if not target_path.is_file():
            print(f"WARNING: skipping {rel}: file not found.")
            skipped.append(rel)
            continue

        target_package = _java_package_of(target_path) if language == "java" else ""
        entities_in_file = closure.qualnames_in_file(rel)
        if not entities_in_file:
            print(f"WARNING: skipping {rel}: no entities found in closure for this file.")
            skipped.append(rel)
            continue

        # Per-file TRAJECTORY subdir, kept under artifacts/ so the process data
        # (search nodes, test-gen/codegen sessions+workspaces) is separated from
        # the documentation outputs (repo_doc.md, docs/<file>.md).
        safe = rel.replace("/", "_")
        file_output_dir = None
        if output_dir is not None:
            file_output_dir = output_dir / "artifacts" / "files" / safe
            file_output_dir.mkdir(parents=True, exist_ok=True)

        # b0) Early-skip files that have no testable concrete behavior (a pure
        #     interface with no method bodies, or an annotation type). Test
        #     generation would only grind for minutes and then fail, so go
        #     straight to the baseline-doc-only / vacuous phi=1.0 path.
        if language == "java":
            untestable = _untestable_java_reason(target_path)
            if untestable:
                _document_no_tests(rel, target_path, file_output_dir, safe, untestable)
                continue

        # b1) Obtain a test suite for F against the ground-truth closure.
        #     --test-file reuses an EXISTING test (skip generation) so a run can
        #     re-do ONLY DocSearch on an already-validated suite. Otherwise the
        #     ReAct generator writes one. No fixed test-COUNT target (a "write N
        #     tests" bar is vague and lets the agent stop early); thoroughness is
        #     gated by real JaCoCo line/branch COVERAGE of the target class
        #     (>=70% line / >=60% branch), quality by the validator (real method
        #     calls, no mocks). min_tests=0 disables the count gate.
        if args.test_file:
            from types import SimpleNamespace
            reuse_path = Path(args.test_file)
            if not reuse_path.exists():
                print(f"WARNING: skipping {rel}: --test-file not found: {reuse_path}")
                _record_testgen(file_output_dir, rel, status="skipped",
                                reason=f"--test-file not found: {reuse_path}")
                skipped.append(rel)
                continue
            print(f"Reusing existing test (skipping test-gen): {reuse_path}")
            test_suite = SimpleNamespace(
                test_file_path=str(reuse_path),
                test_file_content=reuse_path.read_text(encoding="utf-8",
                                                        errors="replace"),
            )
        else:
            try:
                tg_config = TestGeneratorConfig(
                    llm_model=args.hint_model, verbose=False, min_tests=0
                )
                test_suite = ReactTestGenerator(
                    tg_config,
                    dependency_classpath=closure.deps_classpath,
                    target_package=target_package,
                    repo_root=str(repo_root),
                    entities=entities_in_file,
                ).generate(
                    str(target_path), language=language,
                    artifact_dir=str(file_output_dir) if file_output_dir else None,
                )
            except Exception as exc:  # never abort the whole repo for one file
                print(f"WARNING: skipping {rel}: test generation failed: {exc}")
                _record_testgen(file_output_dir, rel, status="skipped",
                                reason=f"test generation error: {exc}")
                skipped.append(rel)
                continue

        test_path = test_suite.test_file_path
        if not test_path or not Path(test_path).exists():
            # Test generation ran but produced no usable tests (e.g. a hard-to-
            # instantiate abstract class). No test signal -> document at vacuous
            # phi=1.0 with the baseline doc only, no search.
            _document_no_tests(rel, target_path, file_output_dir, safe,
                               "no tests could be generated")
            continue
        print(f"Generated tests: {test_path}")

        # Persist the generated test suite + a record IMMEDIATELY — before the
        # (long) search — so the suite is captured even if the search is short,
        # interrupted, or the file is later skipped.
        if file_output_dir is not None:
            try:
                import shutil
                shutil.copy2(test_path, file_output_dir / Path(test_path).name)
            except OSError:
                pass
            _record_testgen(
                file_output_dir, rel, status="generated",
                test_file=Path(test_path).name,
                num_tests=(test_suite.test_file_content or "").count("@Test")
                if language == "java"
                else len(re.findall(r"^\s*def\s+test", test_suite.test_file_content or "", re.M)),
            )

        # b2) Build Module(F entities only) + initial_docs(F) from F alone.
        module, initial_docs, repo = build_module_docs_and_repo(
            str(target_path), hint_llm, language=language
        )
        print(
            f"Module: {module.name}  entities={len(module.entities)}  "
            f"edges={len(module.edges)}"
        )
        entities = list(module.entities)
        target_module = target_package or Path(rel).stem
        source_class_name = target_path.stem if language == "java" else ""

        # b3) Evaluator + code-gen, both wired to the closure.
        if language == "java":
            test_executor = JavaTestExecutor(
                test_suite_path=test_path,
                target_module=target_module,
                repo_path=str(repo_root),
                dependency_classpath=closure.deps_classpath,
                target_package=target_package,
                entities=entities,
                target_class=source_class_name,
            )
            env_status = test_executor.check_environment()
            if not env_status["java_found"] or not env_status["javac_found"]:
                print(f"WARNING: Java environment issues: {env_status['errors']}")

            import shutil
            balanced_test_path = Path(test_path).with_suffix(".balanced.java")
            shutil.copy2(test_path, balanced_test_path)
            test_executor.test_suite_path = balanced_test_path
            test_executor.balance_tests(max_per_entity=2, verbose=False)

            evaluator = JavaEvaluator(
                test_executor=test_executor,
                target_module=target_module,
                repo_path=str(repo_root),
                source_class_name=source_class_name,
                entities=entities,
                dependency_classpath=closure.deps_classpath,
                target_package=target_package,
            )
        else:
            test_executor = TestExecutor(
                test_suite_path=test_path,
                target_module=target_module,
                repo_path=str(repo_root),
                target_rel=rel,
            )
            evaluator = PythonEvaluator(
                test_executor=test_executor,
                target_module=target_module,
                repo_path=str(repo_root),
                entities=entities,
            )

        codegen = AgentCodeGenerator(
            code_llm,
            language=language,
            # Larger files + repo_sources lookups need more director turns than
            # the single-file default; too few and the agent can run out of
            # budget mid-exploration without ever writing the target.
            budget=28,
            dependency_classpath=closure.deps_classpath,
            target_package=target_package,
            artifact_dir=str(file_output_dir) if file_output_dir else None,
            repo_root=str(repo_root),
            target_rel=rel,
        )

        on_step = _make_artifact_saver(file_output_dir, language) if file_output_dir else None

        print(f"\nStarting DocSearch with budget={args.budget}, width={args.width}")
        result = run_search(
            module,
            initial_docs,
            codegen,
            evaluator,
            search_llm,
            config=SearchConfig(
                budget=args.budget,
                inner=InnerConfig(beam_width=args.width),
            ),
            on_step=on_step,
        )

        best_node = result.best_node
        best_phi = (
            sum(best_node.phi.values()) / len(best_node.phi) if best_node.phi else 0.0
        )
        print(f"  best mean φ={best_phi:.3f}  iterations={result.iterations}")

        # (The generated test suite was already persisted right after test-gen,
        # before the search — see _record_testgen above.)
        per_file_results.append({
            "file": rel,
            "entities": len(module.entities),
            "best_mean_phi": best_phi,
            "iterations": result.iterations,
            "budget_fully_used": result.iterations >= args.budget,
            "intractable": list(result.intractable),
        })

        # Write this file's refined documentation as its own markdown, under
        # docs/ — separated from the trajectory artifacts.
        if output_dir is not None:
            try:
                docs_dir = output_dir / "docs"
                docs_dir.mkdir(parents=True, exist_ok=True)
                (docs_dir / f"{safe}.md").write_text(
                    _assemble_final_doc(repo, best_node.docs, language, llm=hint_llm)
                )
            except Exception as exc:
                print(f"WARNING: could not write per-file doc for {rel}: {exc}")

        # c) Collect F's refined per-entity docs + its parsed file structure.
        aggregated_prose.update(best_node.docs)
        aggregated_files.extend(repo.files)
        processed.append(rel)

    if not processed:
        print("\nNo files were optimized; nothing to write.")
        return

    print("\n" + "=" * 60)
    print(f"Repo complete. Processed {len(processed)} file(s); skipped {len(skipped)}.")
    if skipped:
        print(f"Skipped: {skipped}")

    # c) Aggregate every file's refined docs into one repo document.
    repo_struct = RepoStructure(
        project_name=repo_root.name,
        language=language,
        files=aggregated_files,
    )
    final_doc = _assemble_final_doc(repo_struct, aggregated_prose, language, llm=hint_llm)

    # Backup the completed repo run (refined doc + per-file result.json).
    _save_run_backup(output_dir, final_doc=final_doc, result_meta={
        "status": "completed",
        "mode": "repo",
        "repo": str(repo_root),
        "language": language,
        "budget": args.budget,
        "width": args.width,
        "files_processed": processed,
        "files_skipped": skipped,
        "budget_fully_used": bool(per_file_results) and all(
            r["budget_fully_used"] for r in per_file_results
        ),
        "per_file": per_file_results,
        "timestamp": datetime.now().isoformat(),
    })

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(final_doc)
        print(f"\nFinal repo document saved to: {output_path}")
    else:
        print(f"\n{'=' * 60}")
        print("FINAL DOCUMENT:")
        print(f"{'=' * 60}")
        print(final_doc)


def main():
    parser = argparse.ArgumentParser(description="DocSearch: Bilevel tree search for specification optimization")
    parser.add_argument("--module", required=True,
                        help="Source file path (e.g., dataset/python/stocktrends/indicators.py) "
                             "or module name (requires --dataset-root)")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="Total budget (LLM calls)")
    parser.add_argument("--width", type=int, default=W, help="Width W: max attempts per entity")
    parser.add_argument("--hint-model", default="gpt-5.2-us", help="LLM model for hint generation")
    parser.add_argument("--code-model", default="gpt-5.2-us", help="LLM model for code generation")
    parser.add_argument("--dataset-root", default=None, help="Path to dataset root")
    parser.add_argument("--output-dir", default=None, help="Output directory for artifacts")
    parser.add_argument("--resume", default=None, help="Resume from a previous run directory")
    parser.add_argument("--manual-mode", action="store_true",
                        help="Manual mode: pause at each entity for user to provide 5 docs")
    parser.add_argument("--test-file", default=None,
                        help="Path to custom test file (overrides default detection)")
    parser.add_argument("--target-file", default=None,
                        help="Repo mode (--module is a repo dir): optimize just this one "
                             "source file (repo-relative or absolute path). If omitted, all "
                             "non-test source files are optimized.")
    parser.add_argument("--max-files", type=int, default=0,
                        help="Repo mode: cap the number of source files optimized when "
                             "--target-file is omitted (0 = no cap).")
    parser.add_argument("--target-dir", default=None,
                        help="Repo mode: optimize only source files under this sub-path "
                             "(repo-relative, e.g. src/main/java/org/jsoup/select). The "
                             "dependency closure is still built from the whole --module repo "
                             "so compilation sees all dependencies.")
    parser.add_argument("--no-perturbation", action="store_true",
                        help="Disable perturbations (test error sampling only)")
    parser.add_argument("--language", default="python", choices=["python", "java"],
                        help="Programming language: python or java")
    parser.add_argument("--debug-budget", type=int, default=0,
                        help="Max code debug attempts per node for assertion failures (0=disabled)")
    parser.add_argument("-o", "--output", default=None,
                        help="Path to save the final refined document (e.g., output/doc.md)")
    parser.add_argument("--save-artifacts", action="store_true",
                        help="Save intermediate artifacts (tree, node info, etc.)")
    parser.add_argument("--generate-baseline", action="store_true",
                        help="Generate baseline doc from source code and exit (or save with -o)")
    parser.add_argument("--baseline-doc", default=None,
                        help="Path to baseline doc (overrides auto-detection)")

    args = parser.parse_args()

    effective_budget = args.budget
    effective_width = args.width

    # Auto-detect language from file extension if module is a file path
    module_path_obj = Path(args.module)
    if module_path_obj.exists() and module_path_obj.is_dir():
        # Directory (repo): detect the dominant source extension.
        args.language = _detect_directory_language(module_path_obj)
        module_display_name = module_path_obj.name
        repo_mode = True
        if args.target_file:
            module_display_name = Path(args.target_file).stem
    elif module_path_obj.exists() and module_path_obj.is_file():
        repo_mode = False
        if module_path_obj.suffix == ".java":
            args.language = "java"
        elif module_path_obj.suffix == ".py":
            args.language = "python"
        # Derive display name for output dir (e.g., "stocktrends")
        module_display_name = module_path_obj.parent.name
    else:
        repo_mode = False
        module_display_name = args.module
        # Set default dataset root if not using file path mode
        if args.dataset_root is None:
            if args.language == "java":
                args.dataset_root = Path(__file__).parent.parent / "dataset" / "java"
            else:
                args.dataset_root = Path(__file__).parent.parent / "dataset" / "python"

    # Handle --generate-baseline mode
    if args.generate_baseline:
        _generate_baseline(args)
        return

    # Create artifact directory only if --save-artifacts is set
    if args.save_artifacts:
        if args.output_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = Path(__file__).parent.parent / "artifacts" / f"docsearch_{module_display_name}_{args.language}_{effective_budget}_{timestamp}"
        else:
            output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Artifact directory: {output_dir}")
    else:
        output_dir = None

    # Deprecated flags become no-ops on the new pipeline (shared by both modes).
    if args.resume:
        print("WARNING: --resume is no longer supported and will be ignored.")
    if args.manual_mode:
        print("WARNING: --manual-mode is no longer supported and will be ignored.")
    if args.no_perturbation:
        print("WARNING: --no-perturbation is no longer supported and will be ignored.")
    if args.debug_budget:
        print("WARNING: --debug-budget is no longer supported and will be ignored.")

    # Repo mode: --module is a directory -> optimize the repo file-by-file
    # against a fixed ground-truth closure. (Single-file / self-contained
    # behavior below is unchanged.)
    if repo_mode:
        print(f"Repo mode: optimizing {args.module} file-by-file (language: {args.language})")
        hint_llm = make_agent_llm(args.hint_model)
        code_llm = make_agent_llm(args.code_model)
        search_llm = hint_llm
        run_repo(args, hint_llm, code_llm, search_llm, module_path_obj, output_dir)
        return

    # Load module data
    print(f"Loading module: {args.module} (language: {args.language})")
    data = load_module_data(args.module, args.dataset_root, args.test_file, args.language, args.baseline_doc)

    print(f"Entities: {data['entities']}")
    print(f"Test path: {data['test_path']}")
    print(f"Language: {args.language}")

    # Save run config (only if saving artifacts)
    if output_dir:
        run_config = {
            "module": args.module,
            "method": "docsearch",
            "budget": effective_budget,
            "width": effective_width,
            "original_budget": args.budget,
            "original_width": args.width,
            "hint_model": args.hint_model,
            "code_model": args.code_model,
            "entities": data["entities"],
            "test_path": data["test_path"],
            "timestamp": datetime.now().isoformat(),
            "language": args.language,
            "debug_budget": args.debug_budget,
        }
        with open(output_dir / "config.json", "w") as f:
            json.dump(run_config, f, indent=2)

    # Initialize LLM clients - different models for refinement and code generation
    hint_llm = make_agent_llm(args.hint_model)
    code_llm = make_agent_llm(args.code_model)

    print(f"Refinement model: {args.hint_model}")
    print(f"Code model: {args.code_model}")

    # 1) Build/parse the repo via docgen -> search Module + initial per-entity docs.
    #    The parsed RepoStructure is retained for final markdown re-assembly.
    print("Building module + initial docs via docgen...")
    # Build the module from the SOURCE the user pointed at (a single file or a
    # repo dir), NOT data["module_path"] (the dataset base dir), so sibling
    # test files are not mistaken for source entities.
    module, initial_docs, repo = build_module_docs_and_repo(
        args.module, hint_llm, language=args.language
    )
    print(f"Module: {module.name}  entities={len(module.entities)}  edges={len(module.edges)}")

    # 2) Build the Evaluator for the language from the located test file + target
    #    module + repo path (hidden-test signal; never seen by code-gen).
    entities = list(module.entities)
    source_class_name = Path(args.module).stem if args.language == "java" else ""

    if args.language == "java":
        test_executor = JavaTestExecutor(
            test_suite_path=data["test_path"],
            target_module=data["target_module"],
            repo_path=data["module_path"],
            entities=entities,
        )
        env_status = test_executor.check_environment()
        if not env_status["java_found"] or not env_status["javac_found"]:
            print(f"WARNING: Java environment issues: {env_status['errors']}")
        else:
            print(f"Java version: {env_status['java_version']}")

        # Balance test distribution on a copy so the original test file is intact.
        import shutil
        balanced_test_path = Path(data["test_path"]).with_suffix(".balanced.java")
        shutil.copy2(data["test_path"], balanced_test_path)
        test_executor.test_suite_path = balanced_test_path
        test_executor.balance_tests(max_per_entity=2, verbose=False)

        evaluator = JavaEvaluator(
            test_executor=test_executor,
            target_module=data["target_module"],
            repo_path=data["module_path"],
            source_class_name=source_class_name,
            entities=entities,
        )
    else:
        test_executor = TestExecutor(
            test_suite_path=data["test_path"],
            target_module=data["target_module"],
            repo_path=data["module_path"],
        )
        evaluator = PythonEvaluator(
            test_executor=test_executor,
            target_module=data["target_module"],
            repo_path=data["module_path"],
            entities=entities,
        )

    # 3) CodeGenerator = ReAct agent with COMPILE/SMOKE-only feedback (never sees tests).
    codegen = AgentCodeGenerator(code_llm, language=args.language)

    # 4) The search LLM (drives inner diagnose/prescribe).
    search_llm = hint_llm

    # 5) Run the bi-level search. --budget -> SearchConfig.budget,
    #    --width -> InnerConfig.beam_width.
    # Trajectory under artifacts/ so it is separated from the doc outputs.
    on_step = _make_artifact_saver(output_dir / "artifacts") if output_dir else None

    print(f"Method: DocSearch (bi-level search)")
    print(f"\nStarting DocSearch with budget={effective_budget}, width={effective_width}")
    print("=" * 60)

    result = run_search(
        module,
        initial_docs,
        codegen,
        evaluator,
        search_llm,
        config=SearchConfig(
            budget=effective_budget,
            inner=InnerConfig(beam_width=effective_width),
        ),
        on_step=on_step,
    )

    best_node = result.best_node
    best_phi = (
        sum(best_node.phi.values()) / len(best_node.phi) if best_node.phi else 0.0
    )

    print("=" * 60)
    print(f"\nSearch complete!")
    print(f"Best mean φ: {best_phi:.3f}")
    print(f"Iterations: {result.iterations}")
    print(f"Intractable entities: {result.intractable}")
    if result.implicit_edges_discovered:
        print(f"Implicit edges discovered: {result.implicit_edges_discovered}")

    print(f"\nPer-entity φ (best node):")
    for entity, phi in sorted(best_node.phi.items()):
        print(f"  [{entity}] φ={phi:.3f}")

    # 6) Re-assemble the best node's per-entity docs into canonical markdown.
    final_doc = _assemble_final_doc(repo, best_node.docs, args.language, llm=hint_llm)

    # Backup a completed run (refined doc + result.json) when saving artifacts.
    _save_run_backup(output_dir, final_doc=final_doc, result_meta={
        "status": "completed",
        "mode": "file",
        "module": args.module,
        "language": args.language,
        "budget": effective_budget,
        "width": effective_width,
        "iterations": result.iterations,
        "budget_fully_used": result.iterations >= effective_budget,
        "best_mean_phi": best_phi,
        "per_entity_phi": dict(sorted(best_node.phi.items())),
        "intractable": list(result.intractable),
        "implicit_edges_discovered": [list(e) for e in result.implicit_edges_discovered],
        "timestamp": datetime.now().isoformat(),
    })

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(final_doc)
        print(f"\nFinal document saved to: {output_path}")
    else:
        print(f"\n{'=' * 60}")
        print("FINAL DOCUMENT:")
        print(f"{'=' * 60}")
        print(final_doc)


if __name__ == "__main__":
    main()
