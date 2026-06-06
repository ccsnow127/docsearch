"""
Shared data model for the documentation-generation subsystem (docgen).

This subsystem parses a source tree (repo) or a single source file into a
structural model, generates per-object behavioral prose with an LLM, and
assembles everything into the project's canonical baseline-doc format.

The canonical doc format (consumed downstream by entity-level refinement) is:

    # <Project> Baseline Documentation

    ## Module: <ModuleName>
    <one sentence>

    ---

    ## Class: ClassName

    **Interface:**
    ```<lang>
    <signature / fields / method signatures>
    ```

    ### Method: ClassName.methodName
    <behavior prose>

    ---

    ## Function: functionName
    <behavior prose>

Heading patterns (`## Class:`, `## Function:`, `### Method: Class.method`,
`## Module:`) are a hard contract — the entity extractor and entity-level
doc splitter depend on them exactly. All headings are emitted by the
assembler from structural data, NOT by the LLM, so the format is guaranteed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# Object type constants. Use these exact strings everywhere.
OBJ_CLASS = "class"
OBJ_FUNCTION = "function"  # standalone function (no parent class)
OBJ_METHOD = "method"      # function defined inside a class


@dataclass
class CodeObject:
    """A single documentable code object (class, standalone function, or method).

    `qualified_name` is the identity used by the canonical doc format and the
    downstream entity extractor:
      - class            -> "ClassName"
      - standalone func   -> "functionName"
      - method            -> "ClassName.methodName"   (dot-qualified)
      - constructor       -> Python: "ClassName.__init__"
                             Java:   "ClassName constructor"  (matches the
                             existing baseline format for Java constructors)
    """

    obj_type: str                       # OBJ_CLASS | OBJ_FUNCTION | OBJ_METHOD
    name: str                           # simple name, e.g. "compute"
    qualified_name: str                 # see docstring above
    parent: Optional[str] = None        # enclosing class's qualified_name, or None
    params: List[str] = field(default_factory=list)  # parameter names (no `self`/`this`)
    signature: str = ""                 # one-line signature, NO body, e.g. "public double compute(int x)"
    start_line: int = 0
    end_line: int = 0
    code: str = ""                      # full source text of this object
    language: str = "python"            # "python" | "java"
    is_constructor: bool = False
    have_return: bool = False           # whether the body contains a return with a value
    # For classes only: declared field/constant lines (verbatim, no bodies),
    # e.g. ["public String name;", "CONSTANT: int = 0"].
    fields: List[str] = field(default_factory=list)
    # For classes only: qualified_names of direct child methods, in source order.
    children: List[str] = field(default_factory=list)


@dataclass
class FileStructure:
    """Parsed structure of one source file."""

    file_path: str                      # path relative to the repo root (or "<source>" for inline)
    module_name: str                    # derived module name, e.g. "indicators" / "Indicators"
    language: str                       # "python" | "java"
    source_code: str                    # full file source
    # All objects in the file, sorted by start_line ascending.
    objects: List[CodeObject] = field(default_factory=list)

    def classes(self) -> List[CodeObject]:
        return [o for o in self.objects if o.obj_type == OBJ_CLASS]

    def functions(self) -> List[CodeObject]:
        return [o for o in self.objects if o.obj_type == OBJ_FUNCTION]

    def methods_of(self, class_qualified_name: str) -> List[CodeObject]:
        return [
            o for o in self.objects
            if o.obj_type == OBJ_METHOD and o.parent == class_qualified_name
        ]


@dataclass
class RepoStructure:
    """Parsed structure of a whole repository (one or more files)."""

    project_name: str
    language: str                       # dominant language of the repo
    files: List[FileStructure] = field(default_factory=list)

    def all_objects(self) -> List[CodeObject]:
        out: List[CodeObject] = []
        for f in self.files:
            out.extend(f.objects)
        return out
