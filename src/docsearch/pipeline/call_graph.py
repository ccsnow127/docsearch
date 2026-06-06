"""AST-based call graph extraction.

Two AST passes: one to register every function/class/method, another to
record call edges. The resolver recognises three forms:

* bare ``foo(...)`` -> top-level ``foo`` if it exists
* ``Cls.foo(...)`` -> method ``Cls.foo``
* ``self.foo(...)`` inside class ``Cls`` -> ``Cls.foo``

Anything unresolvable statically is dropped; the runtime worthy check
catches missed edges.
"""
from __future__ import annotations

import ast

from docsearch.pipeline.entities import Entity, EntityKind, Module


def extract_module(source: str, *, module_name: str = "module") -> Module:
    """Parse ``source`` and return a populated :class:`Module`."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ValueError(f"failed to parse module '{module_name}': {e}") from e

    module = Module(name=module_name, source=source)

    # Pass 1: collect entities (with their source extents).
    src_lines = source.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module.add_entity(_make_function_entity(node, src_lines))
        elif isinstance(node, ast.ClassDef):
            cls_entity = _make_class_entity(node, src_lines)
            module.add_entity(cls_entity)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    module.add_entity(
                        _make_method_entity(node.name, item, src_lines)
                    )

    # Pass 2: collect edges.
    for caller_qn, callees in _collect_calls(tree, module).items():
        for callee in callees:
            module.add_edge(caller_qn, callee)

    return module


# --------------------------------------------------------------------------
# Entity construction
# --------------------------------------------------------------------------

def _segment(node: ast.AST, src_lines: list[str]) -> str:
    """Best-effort source extraction; ``ast.get_source_segment`` is fine
    but fails on some edge cases when the source lacks a trailing newline."""
    try:
        seg = ast.get_source_segment("\n".join(src_lines) + "\n", node)
        if seg:
            return seg
    except Exception:
        pass
    start = getattr(node, "lineno", 1) - 1
    end = getattr(node, "end_lineno", start + 1)
    return "\n".join(src_lines[start:end])


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    try:
        args_src = ast.unparse(node.args)
    except Exception:  # pragma: no cover
        return f"def {node.name}(...)"
    return f"def {node.name}({args_src})".replace("\n", " ")


def _make_function_entity(
    node: ast.FunctionDef | ast.AsyncFunctionDef, src_lines: list[str]
) -> Entity:
    return Entity(
        qualname=node.name,
        kind=EntityKind.FUNCTION,
        signature=_signature(node),
        source=_segment(node, src_lines),
    )


def _make_class_entity(node: ast.ClassDef, src_lines: list[str]) -> Entity:
    bases = ", ".join(ast.unparse(b) for b in node.bases) if node.bases else ""
    sig = f"class {node.name}" + (f"({bases})" if bases else "")
    return Entity(
        qualname=node.name,
        kind=EntityKind.CLASS,
        signature=sig,
        source=_segment(node, src_lines),
    )


def _make_method_entity(
    cls_name: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    src_lines: list[str],
) -> Entity:
    return Entity(
        qualname=f"{cls_name}.{node.name}",
        kind=EntityKind.METHOD,
        signature=_signature(node),
        source=_segment(node, src_lines),
    )


# --------------------------------------------------------------------------
# Edge resolution
# --------------------------------------------------------------------------

def _collect_calls(tree: ast.Module, module: Module) -> dict[str, set[str]]:
    edges: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            edges[node.name] = _calls_in(node, module, cls_context=None)
        elif isinstance(node, ast.ClassDef):
            # Class init / direct body is part of the class entity itself.
            cls_calls: set[str] = set()
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qn = f"{node.name}.{item.name}"
                    edges[qn] = _calls_in(item, module, cls_context=node.name)
                else:
                    cls_calls |= _calls_in(item, module, cls_context=node.name)
            edges[node.name] = cls_calls
    return edges


def _calls_in(
    func_node: ast.AST, module: Module, *, cls_context: str | None
) -> set[str]:
    callees: set[str] = set()
    for sub in ast.walk(func_node):
        if not isinstance(sub, ast.Call):
            continue
        target = _resolve_call(sub.func, module, cls_context=cls_context)
        if target:
            callees.add(target)
    return callees


def _resolve_call(
    func: ast.expr, module: Module, *, cls_context: str | None
) -> str | None:
    if isinstance(func, ast.Name):
        # foo(...)
        return func.id if func.id in module.entities else None

    if isinstance(func, ast.Attribute):
        # X.method(...) — three sub-cases
        if isinstance(func.value, ast.Name):
            base = func.value.id
            if base == "self" and cls_context:
                qn = f"{cls_context}.{func.attr}"
                return qn if qn in module.entities else None
            qn = f"{base}.{func.attr}"
            if qn in module.entities:
                return qn
            if base in module.entities:
                return base  # treat as call into class entity
    return None
