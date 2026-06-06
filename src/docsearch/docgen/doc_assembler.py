"""
Deterministic assembler for the canonical baseline-doc format.

This component is the format guarantor of the docgen subsystem. It takes a
parsed :class:`RepoStructure`, a mapping of behavioral prose (produced by the
LLM, one string per code object) and optional one-sentence module summaries,
and emits the project's canonical baseline documentation.

ALL markdown structure -- the top title, ``## Module:`` / ``## Class:`` /
``## Function:`` / ``### Method:`` headings, the ``**Interface:**`` fenced
code block, and the ``---`` dividers -- is produced here from structural (AST)
data. The LLM only ever contributes behavior prose. This separation is what
makes the output format provably conformant with the downstream entity
extractor and the entity-level doc splitter.

The emitted heading patterns are a hard contract:

  - ``# <Project> Baseline Documentation``
  - ``## Module: <ModuleName>``
  - ``## Class: ClassName``
  - ``### Method: ClassName.methodName``  (dot-qualified; Java constructors use
    ``### Method: ClassName constructor``)
  - ``## Function: functionName``

Class sections are separated by a line containing only ``---``.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from docsearch.docgen.models import (
    OBJ_CLASS,
    OBJ_FUNCTION,
    OBJ_METHOD,
    CodeObject,
    FileStructure,
    RepoStructure,
)


# Fallback module summary when none is supplied and none can be inferred.
_DEFAULT_MODULE_SUMMARY = "Source module documented by the baseline generator."


class DocAssembler:
    """Assembles a :class:`RepoStructure` plus prose into canonical baseline docs.

    The single public entry point is :meth:`assemble`. The class holds no
    mutable state between calls, so a single instance may be reused.
    """

    def assemble(
        self,
        repo: RepoStructure,
        prose: Dict[str, str],
        module_descriptions: Optional[Dict[str, str]] = None,
    ) -> str:
        """Render the full baseline document.

        Args:
            repo: Parsed repository structure.
            prose: Maps ``CodeObject.qualified_name`` to a behavioral prose
                string (no markdown headings / dividers / code fences).
            module_descriptions: Optional map of ``module_name`` to a
                one-sentence module summary.

        Returns:
            The complete baseline documentation as a single string.
        """
        prose = prose or {}
        module_descriptions = module_descriptions or {}

        parts: List[str] = []
        parts.append(f"# {repo.project_name} Baseline Documentation")

        for file in repo.files:
            parts.append("")
            parts.append(self._render_file(file, prose, module_descriptions))

        # Single trailing newline, no duplicate blank lines at the boundaries.
        return "\n".join(parts).rstrip() + "\n"

    # ------------------------------------------------------------------ #
    # File / module level
    # ------------------------------------------------------------------ #
    def _render_file(
        self,
        file: FileStructure,
        prose: Dict[str, str],
        module_descriptions: Dict[str, str],
    ) -> str:
        parts: List[str] = []

        summary = module_descriptions.get(file.module_name) or _DEFAULT_MODULE_SUMMARY
        parts.append(f"## Module: {file.module_name}")
        parts.append("")
        parts.append(summary.strip())
        parts.append("")
        parts.append("---")

        # Classes (each its own section, separated by ---) then standalone
        # functions, all in source order within their groups.
        for cls in file.classes():
            parts.append("")
            parts.append(self._render_class(file, cls, prose))
            parts.append("")
            parts.append("---")

        functions = file.functions()
        for func in functions:
            parts.append("")
            parts.append(self._render_function(func, prose, file))
            parts.append("")
            parts.append("---")

        # Drop the final divider if the file produced any sections; the file
        # boundary itself already separates modules.
        if parts and parts[-1] == "---":
            parts.pop()
            if parts and parts[-1] == "":
                parts.pop()

        return "\n".join(parts).rstrip()

    # ------------------------------------------------------------------ #
    # Class level
    # ------------------------------------------------------------------ #
    def _render_class(
        self,
        file: FileStructure,
        cls: CodeObject,
        prose: Dict[str, str],
    ) -> str:
        parts: List[str] = []
        parts.append(f"## Class: {cls.name}")
        parts.append("")
        parts.append("**Interface:**")
        parts.append(self._render_interface_block(file, cls))

        # Emit one section per UNIQUE qualified_name. Overloaded methods /
        # constructors share a qualified_name (Java has no param-type in ours),
        # so they are listed individually in the interface block above but get a
        # single ``### Method:`` section here — duplicate headings would break
        # the downstream entity splitter (_extract/_replace_entity_doc).
        seen: set = set()
        for method in self._methods_in_source_order(file, cls):
            if method.qualified_name in seen:
                continue
            seen.add(method.qualified_name)
            parts.append("")
            parts.append(f"### Method: {method.qualified_name}")
            parts.append("")
            parts.append(self._prose_for(method, prose, file))

        return "\n".join(parts)

    def _render_interface_block(self, file: FileStructure, cls: CodeObject) -> str:
        """Build the fenced ``**Interface:**`` code block for a class.

        The block reproduces the class signature, its declared fields/constants,
        and the no-body signatures of every direct method (constructors first,
        then the rest), all in source order.
        """
        lang = cls.language or file.language or "python"
        indent = "    "

        lines: List[str] = ["```" + lang]

        signature = (cls.signature or f"class {cls.name}").rstrip()
        # Java-style signatures carry their own opening brace; Python-style ones
        # use a trailing colon. Honor whatever the parser produced, otherwise
        # add a sensible default opener for the language.
        if signature.endswith("{") or signature.endswith(":"):
            lines.append(signature)
        elif lang == "java":
            lines.append(signature + " {")
        else:
            lines.append(signature + ":")

        methods = self._methods_in_source_order(file, cls)
        constructors = [m for m in methods if m.is_constructor]
        regular = [m for m in methods if not m.is_constructor]

        if cls.fields:
            lines.append("")
            for field_line in cls.fields:
                lines.append(indent + field_line.rstrip())

        if constructors:
            lines.append("")
            for ctor in constructors:
                lines.append(indent + self._method_signature(ctor))

        if regular:
            lines.append("")
            for method in regular:
                lines.append(indent + self._method_signature(method))

        if lang == "java":
            lines.append("}")

        lines.append("```")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Function level
    # ------------------------------------------------------------------ #
    def _render_function(
        self,
        func: CodeObject,
        prose: Dict,
        file: "FileStructure | None" = None,
    ) -> str:
        parts: List[str] = []
        parts.append(f"## Function: {func.name}")
        parts.append("")
        if func.signature:
            lang = func.language or "python"
            parts.append("```" + lang)
            parts.append(func.signature.rstrip())
            parts.append("```")
            parts.append("")
        parts.append(self._prose_for(func, prose, file))
        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _methods_in_source_order(
        self, file: FileStructure, cls: CodeObject
    ) -> List[CodeObject]:
        """Return the class's direct methods, ordered as in the source.

        Returns ALL direct methods (including overloads that share a
        qualified_name) in source order, so the interface block can list each
        overload's own signature. Prefers parent linkage; falls back to the
        recorded ``children`` ordering.
        """
        methods = file.methods_of(cls.qualified_name)
        if methods:
            return methods
        # Fallback: reconstruct from the class's recorded children order. Keep
        # every occurrence (do not collapse overloads) by consuming matches in
        # order.
        remaining = [o for o in file.objects if o.obj_type == OBJ_METHOD]
        ordered: List[CodeObject] = []
        for qname in cls.children or []:
            for i, obj in enumerate(remaining):
                if obj.qualified_name == qname:
                    ordered.append(remaining.pop(i))
                    break
        return ordered

    def _method_signature(self, method: CodeObject) -> str:
        if method.signature:
            return method.signature.rstrip()
        # Construct a minimal, body-free signature from available pieces.
        params = ", ".join(method.params)
        if method.language == "java":
            return f"{method.name}({params})"
        return f"def {method.name}({params})"

    def _prose_for(
        self,
        obj: CodeObject,
        prose: Dict,
        file: "FileStructure | None" = None,
    ) -> str:
        # Prefer a file-scoped key ``(file_path, qualified_name)`` so that two
        # files declaring the same qualified_name (e.g. a ``Tag`` class in three
        # files, or a shared ``Base.url`` method) never share prose. Fall back to
        # the flat ``qualified_name`` key for callers that pass a flat dict.
        candidates = []
        if file is not None:
            candidates.append((file.file_path, obj.qualified_name))
        candidates.append(obj.qualified_name)
        for key in candidates:
            text = prose.get(key)
            if text and text.strip():
                return text.strip()
        return self._placeholder(obj)

    def _placeholder(self, obj: CodeObject) -> str:
        if obj.obj_type == OBJ_CLASS:
            return f"Defines the `{obj.name}` type."
        if obj.obj_type == OBJ_FUNCTION:
            return f"Implements the `{obj.name}` function."
        if obj.is_constructor:
            return f"Initializes a new `{obj.parent or obj.name}` instance."
        return f"Implements the `{obj.name}` method."
