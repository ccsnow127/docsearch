"""
Repository-level driver for the documentation-generation subsystem (docgen).

This module ties the pieces together: it walks a source tree (or accepts a
single file / inline source), dispatches each file to the appropriate
language parser, generates per-object behavioral prose with an LLM, and hands
everything to the deterministic :class:`DocAssembler` to render the canonical
baseline document.

The orchestration here owns no formatting logic of its own. All markdown
structure (headings, the ``**Interface:**`` block, dividers) is produced by
:class:`DocAssembler` from structural (AST) data, and the only LLM output is
behavior prose. This module simply coordinates parsing, prose generation, and
assembly so that a caller can go from a path (or a string of source) to a
finished baseline document in one call.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Dict, List, Optional

from docsearch.docgen import java_parser, python_parser
from docsearch.docgen.doc_assembler import DocAssembler
from docsearch.docgen.models import FileStructure, RepoStructure
from docsearch.docgen.object_doc_generator import ObjectDocGenerator
from docsearch.llm.factory import build_client
from docsearch.docgen.llm_adapter import LLMClientAdapter

logger = logging.getLogger(__name__)


# Default model used when no LLM client is injected.
_DEFAULT_MODEL = "gpt-5.2-us"

# Directory names that are never walked.
_SKIP_DIRS = {"__pycache__"}

# Extension -> ("language", parser module) dispatch table.
_EXT_LANGUAGE = {
    ".py": "python",
    ".java": "java",
}
_PARSERS = {
    "python": python_parser,
    "java": java_parser,
}


class RepoDocGenerator:
    """Generates canonical baseline documentation for a repository or file.

    Public API:
        ``RepoDocGenerator(llm_client, language=None)``
        ``generate(path: str) -> str``
        ``generate_from_source(source_code, language, name="module") -> str``
    """

    def __init__(self, llm_client=None, language: Optional[str] = None):
        """Set up the generator.

        Args:
            llm_client: An object exposing
                ``generate(prompt, temperature=0, system=None) -> str``. If
                ``None``, a default client is created via
                :func:`create_llm_client`.
            language: Optional forced language (``"python"`` or ``"java"``).
                When set, every file is parsed with that language's parser
                regardless of its extension; otherwise the extension decides.
        """
        client = llm_client if llm_client is not None else build_client(_DEFAULT_MODEL)
        if not hasattr(client, "generate"):
            client = LLMClientAdapter(client)  # release LLMClient -> .generate() contract
        self.llm_client = client
        self.language = language.lower() if language else None
        self.object_doc_generator = ObjectDocGenerator(self.llm_client)
        self.assembler = DocAssembler()

    # ------------------------------------------------------------------ #
    # Public entry points
    # ------------------------------------------------------------------ #
    def generate(self, path: str) -> str:
        """Generate baseline documentation for ``path``.

        Args:
            path: A directory (walked recursively) or a single source file.

        Returns:
            The complete baseline documentation as a single string. Files that
            fail to parse are skipped with a logged warning rather than
            aborting the run.

        Raises:
            FileNotFoundError: If ``path`` does not exist.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Path does not exist: {path}")

        if os.path.isdir(path):
            project_name = os.path.basename(os.path.abspath(path.rstrip(os.sep))) or "project"
            files = self._parse_directory(path)
        else:
            project_name = os.path.splitext(os.path.basename(path))[0] or "project"
            file_struct = self._parse_one_file(path)
            files = [file_struct] if file_struct is not None else []

        repo = self._build_repo(project_name, files)
        return self._assemble(repo)

    def generate_from_source(
        self, source_code: str, language: str, name: str = "module"
    ) -> str:
        """Generate baseline documentation for a single in-memory source string.

        The source is written to a temporary file with the correct extension
        and run through the same pipeline as :meth:`generate`, providing
        back-compat for string input.

        Args:
            source_code: Full source text.
            language: ``"python"`` or ``"java"``.
            name: Project / module stem used in the document title.

        Returns:
            The complete baseline documentation as a single string.

        Raises:
            ValueError: If ``language`` is not supported.
        """
        lang = (language or "").lower()
        if lang not in _PARSERS:
            raise ValueError(
                f"Unsupported language: {language!r}. Expected one of "
                f"{sorted(_PARSERS)}."
            )

        suffix = ".py" if lang == "python" else ".java"
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix=f"{name}_")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(source_code)
            file_struct = self._parse_with_language(tmp_path, source_code, lang)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        if file_struct is None:
            # Parsing failed; produce an (essentially empty) doc rather than
            # crashing, mirroring the directory-walk's skip-and-continue policy.
            file_struct = None
            files: List[FileStructure] = []
        else:
            # Use the caller-supplied name as the module name for nicer output.
            file_struct.module_name = name
            files = [file_struct]

        repo = self._build_repo(name, files)
        return self._assemble(repo)

    # ------------------------------------------------------------------ #
    # Parsing helpers
    # ------------------------------------------------------------------ #
    def _parse_directory(self, root: str) -> List[FileStructure]:
        """Walk ``root`` and parse every supported, non-hidden source file."""
        files: List[FileStructure] = []
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip hidden directories and known noise dirs in-place so os.walk
            # does not descend into them.
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in _SKIP_DIRS
            ]
            for filename in sorted(filenames):
                if filename.startswith("."):
                    continue
                ext = os.path.splitext(filename)[1].lower()
                if self.language is None and ext not in _EXT_LANGUAGE:
                    continue
                if self.language is not None and ext not in _EXT_LANGUAGE:
                    # When a language is forced we still only accept source
                    # files with a recognized extension.
                    continue
                full_path = os.path.join(dirpath, filename)
                file_struct = self._parse_one_file(full_path)
                if file_struct is not None:
                    files.append(file_struct)
        files.sort(key=lambda f: f.file_path)
        return files

    def _parse_one_file(self, path: str) -> Optional[FileStructure]:
        """Read and parse a single file, returning ``None`` on any failure."""
        ext = os.path.splitext(path)[1].lower()
        lang = self.language or _EXT_LANGUAGE.get(ext)
        if lang not in _PARSERS:
            logger.warning("Skipping unsupported file (no parser): %s", path)
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                source_code = handle.read()
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Skipping unreadable file %s: %s", path, exc)
            return None
        return self._parse_with_language(path, source_code, lang)

    def _parse_with_language(
        self, path: str, source_code: str, lang: str
    ) -> Optional[FileStructure]:
        """Parse ``source_code`` with the parser for ``lang``; skip on failure."""
        parser = _PARSERS.get(lang)
        if parser is None:
            logger.warning("Skipping file with unsupported language %r: %s", lang, path)
            return None
        try:
            return parser.parse_file(path, source_code)
        except Exception as exc:  # never abort the run for one bad file
            logger.warning("Skipping file that failed to parse %s: %s", path, exc)
            return None

    # ------------------------------------------------------------------ #
    # Repo assembly
    # ------------------------------------------------------------------ #
    def _build_repo(
        self, project_name: str, files: List[FileStructure]
    ) -> RepoStructure:
        """Bundle parsed files into a RepoStructure with a dominant language."""
        language = self._dominant_language(files)
        return RepoStructure(
            project_name=project_name,
            language=language,
            files=files,
        )

    @staticmethod
    def _dominant_language(files: List[FileStructure]) -> str:
        """Return the most common file language, defaulting to ``"python"``."""
        counts: Dict[str, int] = {}
        for file in files:
            counts[file.language] = counts.get(file.language, 0) + 1
        if not counts:
            return "python"
        return max(counts, key=counts.get)

    def _assemble(self, repo: RepoStructure) -> str:
        """Generate prose for every object and render the final document.

        Per-object docs and per-module overviews are generated CONCURRENTLY (the
        LLM calls are independent and I/O-bound), collapsing N sequential calls
        to ~N/workers wall-clock. Each per-object call still keeps focused,
        independently-refinable per-entity docs with full module context.
        """
        from concurrent.futures import ThreadPoolExecutor

        # Document each file in BATCHED per-module calls (the full source is sent
        # once per batch, not once per entity) + one module-overview call. Files
        # are processed concurrently. prose is keyed by (file, qualified_name) so
        # identical names across files never collide.
        prose: Dict = {}
        module_descriptions: Dict = {}

        def _per_file(file):
            try:
                entity_docs = self.object_doc_generator.generate_module_docs(file)
            except Exception as exc:
                logger.warning("Module-doc generation failed for %s: %s",
                               file.file_path, exc)
                entity_docs = {}
            try:
                overview = self.object_doc_generator.generate_module_overview(file)
            except Exception as exc:
                logger.warning("Module overview failed for %s: %s",
                               file.module_name, exc)
                overview = None
            return file, entity_docs, overview

        files = list(repo.files)
        max_workers = min(8, max(1, len(files)))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for file, entity_docs, overview in pool.map(_per_file, files):
                for qn, doc in entity_docs.items():
                    prose[(file.file_path, qn)] = doc
                if overview is not None:
                    module_descriptions[file.module_name] = overview
        return self.assembler.assemble(repo, prose, module_descriptions)
