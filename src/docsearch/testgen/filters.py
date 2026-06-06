"""Post-validation filters for LLM-generated tests.

* Direct-call requirement: every retained test for entity ``e`` must
  reference ``e``'s name in its body. Tests that reach ``e`` only
  transitively are dropped because their failures cannot localize to
  ``e``.
* Deduplication: tests with the same canonical AST are kept only once
  (``ast.unparse`` after re-parsing collapses whitespace differences).
"""
from __future__ import annotations

import ast

from docsearch.testgen.extract import normalize_test


def references_entity(test_src: str, entity_name: str) -> bool:
    """True iff ``test_src`` syntactically mentions ``entity_name`` as a
    Name, Attribute, or direct call target.

    Special-cases dunder constructors / destructors: tests for
    ``Cls.__init__`` are written as ``Cls(...)`` (not as
    ``Cls.__init__(...)``) so a class-name reference also counts.
    """
    try:
        tree = ast.parse(test_src)
    except SyntaxError:
        return False
    # Class method qualnames are dotted; the *last* segment is what
    # appears in test source (``Calc().add(...)`` for entity ``Calc.add``).
    accepted: set[str] = {entity_name.rsplit(".", 1)[-1]}
    # ``Cls.__init__`` etc. — accept the class-name reference too.
    if "." in entity_name and entity_name.rsplit(".", 1)[-1].startswith("__"):
        accepted.add(entity_name.rsplit(".", 1)[0])
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in accepted:
            return True
        if isinstance(node, ast.Attribute) and node.attr in accepted:
            return True
    return False


def filter_direct(tests: list[str], entity_name: str) -> list[str]:
    return [t for t in tests if references_entity(t, entity_name)]


def deduplicate(tests: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in tests:
        key = normalize_test(t)
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out
