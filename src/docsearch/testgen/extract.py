"""Split an LLM test blob into preamble + per-``test_*`` source strings."""
from __future__ import annotations

import ast
import textwrap

from docsearch.pipeline.code_generator import _strip_code_fences


def extract_tests(blob: str) -> tuple[str, list[str]]:
    """Return ``(preamble, tests)``.

    * ``preamble``: module-level imports + non-test top-level statements
      (e.g., fixtures, helper functions) concatenated as Python source.
    * ``tests``: list of source strings, one per ``def test_*()`` /
      ``async def test_*()``.

    Raises ``ValueError`` on syntax errors.
    """
    cleaned = _strip_code_fences(blob)
    if not cleaned.strip():
        return "", []
    try:
        tree = ast.parse(cleaned)
    except SyntaxError as e:
        raise ValueError(f"failed to parse LLM test output: {e}") from e

    preamble_nodes: list[ast.stmt] = []
    test_nodes: list[ast.stmt] = []
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ):
            test_nodes.append(node)
        else:
            preamble_nodes.append(node)

    preamble = "\n\n".join(ast.unparse(n) for n in preamble_nodes)
    tests = [ast.unparse(n) for n in test_nodes]
    return preamble, tests


def normalize_test(src: str) -> str:
    """Canonical form for dedup: strip comments / blank lines / trailing
    whitespace from each line."""
    try:
        tree = ast.parse(src)
        return ast.unparse(tree)
    except SyntaxError:
        return textwrap.dedent(src).strip()
