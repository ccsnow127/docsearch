"""Python source parsing for the docgen subsystem.

Parses a single Python file into the shared structural model
(:class:`~docsearch.docgen.models.FileStructure`) using the stdlib ``ast``
module. Classes become ``OBJ_CLASS`` objects, top-level functions become
``OBJ_FUNCTION`` objects, and functions defined inside a class become
``OBJ_METHOD`` objects. Only structural data is produced here; behavioral
prose is added later by the LLM stage and all markdown headings are emitted
by the assembler, never by this module.
"""

from __future__ import annotations

import ast
import os
from typing import List, Optional

from docsearch.docgen.models import (
    CodeObject,
    FileStructure,
    OBJ_CLASS,
    OBJ_FUNCTION,
    OBJ_METHOD,
)


def _get_end_lineno(node: ast.AST) -> int:
    """Return the last line number spanned by ``node`` (children included).

    Returns ``-1`` for nodes that carry no line information.
    """
    if not hasattr(node, "lineno"):
        return -1
    end_lineno = node.lineno
    for child in ast.iter_child_nodes(node):
        child_end = getattr(child, "end_lineno", None) or _get_end_lineno(child)
        if child_end > -1:
            end_lineno = max(end_lineno, child_end)
    return end_lineno


def _has_return_value(node: ast.AST) -> bool:
    """Whether ``node``'s own body contains a ``return`` with a value.

    Nested function/class scopes are not descended into, so a ``return`` in an
    inner helper does not count toward the enclosing object.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.Return):
            if child.value is not None:
                return True
        elif isinstance(
            child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        elif _has_return_value(child):
            return True
    return False


def _params(node: ast.AST) -> List[str]:
    """Parameter names for a function node, excluding ``self``/``cls``."""
    args = getattr(node, "args", None)
    if args is None:
        return []
    names: List[str] = []
    for arg in list(args.posonlyargs) + list(args.args):
        names.append(arg.arg)
    if args.vararg is not None:
        names.append(args.vararg.arg)
    for arg in args.kwonlyargs:
        names.append(arg.arg)
    if args.kwarg is not None:
        names.append(args.kwarg.arg)
    return [n for n in names if n not in ("self", "cls")]


def _func_signature(node, source_lines: List[str]) -> str:
    """Best-effort one-line signature for a function, without its body.

    Built from ``ast.unparse`` over the arguments and return annotation; falls
    back to the raw ``def`` line(s) from the source if unparsing fails.
    """
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    try:
        args = ast.unparse(node.args)
        sig = f"{prefix} {node.name}({args})"
        if node.returns is not None:
            sig += f" -> {ast.unparse(node.returns)}"
        return sig
    except Exception:
        start = node.lineno - 1
        end = node.lineno
        # Pull lines up to (but not including) the body's first statement.
        if node.body:
            end = node.body[0].lineno - 1
        raw = " ".join(
            line.strip() for line in source_lines[start:end] if line.strip()
        )
        raw = raw.rstrip()
        if raw.endswith(":"):
            raw = raw[:-1]
        return raw


def _class_signature(node: ast.ClassDef, source_lines: List[str]) -> str:
    """The ``class Foo(Bar):`` header line, without trailing colon."""
    bases: List[str] = []
    try:
        bases = [ast.unparse(b) for b in node.bases]
        bases += [ast.unparse(k) for k in node.keywords]
    except Exception:
        bases = []
    if bases:
        return f"class {node.name}({', '.join(bases)})"
    # No explicit bases: prefer the raw header (preserves "()" if present).
    raw = source_lines[node.lineno - 1].strip()
    if raw.endswith(":"):
        raw = raw[:-1]
    return raw if raw.startswith("class ") else f"class {node.name}"


def _class_field_lines(node: ast.ClassDef, source_lines: List[str]) -> List[str]:
    """Verbatim source lines for class-level annotated/assigned attributes."""
    lines: List[str] = []
    for stmt in node.body:
        if isinstance(stmt, (ast.AnnAssign, ast.Assign)):
            start = stmt.lineno - 1
            end = getattr(stmt, "end_lineno", stmt.lineno)
            text = "\n".join(source_lines[start:end]).strip()
            if text:
                lines.append(text)
    return lines


def _slice(source_lines: List[str], start_line: int, end_line: int) -> str:
    """Source text for the inclusive 1-based line range ``[start, end]``."""
    return "\n".join(source_lines[start_line - 1 : end_line])


def _module_name(file_path: str) -> str:
    base = os.path.basename(file_path)
    name, _ = os.path.splitext(base)
    return name or file_path


def parse_file(file_path: str, source_code: str) -> FileStructure:
    """Parse Python ``source_code`` into a :class:`FileStructure`.

    Args:
        file_path: Path used for the resulting structure (relative to repo root,
            or ``"<source>"`` for inline source). Drives ``module_name``.
        source_code: Full text of the Python file.

    Returns:
        A :class:`FileStructure` whose ``objects`` are classes, standalone
        functions, and methods, sorted by ``start_line``.
    """
    structure = FileStructure(
        file_path=file_path,
        module_name=_module_name(file_path),
        language="python",
        source_code=source_code,
    )

    tree = ast.parse(source_code)
    source_lines = source_code.splitlines()
    objects: List[CodeObject] = []

    def visit(node: ast.AST, class_qualname: Optional[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                qualified_name = child.name
                start_line = child.lineno
                end_line = _get_end_lineno(child)
                obj = CodeObject(
                    obj_type=OBJ_CLASS,
                    name=child.name,
                    qualified_name=qualified_name,
                    parent=class_qualname,
                    params=[],
                    signature=_class_signature(child, source_lines),
                    start_line=start_line,
                    end_line=end_line,
                    code=_slice(source_lines, start_line, end_line),
                    language="python",
                    is_constructor=False,
                    have_return=False,
                )
                # fields: declared class-level attribute lines only (the class
                # signature is carried on obj.signature and emitted separately
                # by the assembler, so it must NOT be duplicated here).
                obj.fields = _class_field_lines(child, source_lines)
                # children: qualified_names of this class's direct methods.
                obj.children = [
                    f"{qualified_name}.{m.name}"
                    for m in child.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                objects.append(obj)
                visit(child, qualified_name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start_line = child.lineno
                end_line = _get_end_lineno(child)
                if class_qualname is not None:
                    obj_type = OBJ_METHOD
                    qualified_name = f"{class_qualname}.{child.name}"
                else:
                    obj_type = OBJ_FUNCTION
                    qualified_name = child.name
                obj = CodeObject(
                    obj_type=obj_type,
                    name=child.name,
                    qualified_name=qualified_name,
                    parent=class_qualname,
                    params=_params(child),
                    signature=_func_signature(child, source_lines),
                    start_line=start_line,
                    end_line=end_line,
                    code=_slice(source_lines, start_line, end_line),
                    language="python",
                    is_constructor=(
                        class_qualname is not None and child.name == "__init__"
                    ),
                    have_return=_has_return_value(child),
                )
                objects.append(obj)
                # Descend: nested functions/classes are top-level relative to
                # their own scope (a class nested in a method is a class).
                visit(child, None)

    visit(tree, None)

    structure.objects = sorted(objects, key=lambda o: o.start_line)
    return structure
