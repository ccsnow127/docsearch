"""Turn a documentation snapshot into a runnable Python module.

Hands the LLM documentation for every entity in the module and asks it
to produce one Python file implementing them all. The result is a string
that the evaluator runs against the test suite. Common LLM artefacts
(markdown fences) are stripped before returning.
"""
from __future__ import annotations

import re
from typing import Mapping

from docsearch.llm.base import LLMClient
from docsearch.pipeline.entities import Entity, Module
from docsearch.prompts import render


def render_documentation(
    module: Module, docs: Mapping[str, str]
) -> str:
    """Format the per-entity documentation block injected into the prompt."""
    lines: list[str] = []
    for qualname, entity in module.entities.items():
        doc = docs.get(qualname, "")
        lines.append(f"### {qualname} ({entity.kind.value})")
        if entity.signature:
            lines.append(f"Signature: {entity.signature}")
        lines.append("Documentation:")
        lines.append(doc.strip() or "(empty)")
        lines.append("")
    return "\n".join(lines).rstrip()


def generate_code(
    module: Module,
    docs: Mapping[str, str],
    llm: LLMClient,
    *,
    temperature: float = 0.7,
    seed: int | None = None,
) -> str:
    """Produce a complete Python implementation of ``module`` from ``docs``.

    Missing keys in ``docs`` render as ``(empty)``; under-specification
    then surfaces during evaluation rather than being silently masked.
    """
    prompt = render(
        "code_generation",
        module_name=module.name,
        all_entity_documentation=render_documentation(module, docs),
    )
    resp = llm.complete(prompt, temperature=temperature, seed=seed)
    return _strip_code_fences(resp.text)


# ---------------------------------------------------------------------------
# Output cleanup
# ---------------------------------------------------------------------------

_FENCE_OPEN = re.compile(r"^\s*```(?:python|py)?\s*\n?", re.IGNORECASE)
_FENCE_CLOSE = re.compile(r"\n?```\s*$")


def _strip_code_fences(text: str) -> str:
    """Remove a single leading/trailing markdown fence if present.

    Only the outermost fence pair is stripped so embedded fences (e.g.
    inside docstrings) survive.
    """
    if not text:
        return ""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _FENCE_OPEN.sub("", stripped, count=1)
        stripped = _FENCE_CLOSE.sub("", stripped)
    return stripped.strip() + "\n"
