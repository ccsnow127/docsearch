"""LLM prompt templates for the inner diagnose -> prescribe stages.

Each template is a ``str.format``-style string. Use :func:`render` to
fill in placeholders; missing keys raise ``KeyError``.

The templates are language-parameterized through a ``{language}`` field
so the same search runs for Java (primary) and Python (secondary).
"""
from __future__ import annotations

from typing import Any


DIAGNOSIS = """\
You are analyzing test failures to diagnose why an LLM failed to generate \
correct {language} code from a given documentation.

Entity Information:
- Name: {entity_name}
- Type: {entity_type}
- Current Documentation:
{current_doc}

Generated Code (produced by the LLM from the current documentation; this is \
the artifact under diagnosis):
{generated_code}

Test Failures:
The generated code failed the following tests:
{error_messages}

Task:
By comparing the generated code against the test failures and the current \
documentation, diagnose:
  1. What went wrong? Identify the specific errors (type mismatches, \
incorrect outputs, missing logic, etc.) visible in the generated code.
  2. Why did the LLM fail? What information is missing or ambiguous in the \
documentation that led to this implementation?
  3. What knowledge gap exists? What does the documentation need to convey \
so that an LLM would not make this same mistake?

Output:
Provide a concise diagnosis in the following format:
- Error Type: [brief description]
- Root Cause: [what the documentation failed to convey]
- Missing Information: [what needs to be clarified in the documentation]
"""


PRESCRIPTION = """\
You are refining documentation for a {language} code entity based on a \
diagnosis of test failures.

Entity Information:
- Name: {entity_name}
- Type: {entity_type}
- Current Documentation:
{current_doc}

Diagnosis:
{diagnosis_output}

Task:
Refine the documentation to address the diagnosed issues. The refined \
documentation should:
  1. Directly address the identified knowledge gap.
  2. Clarify the ambiguous or missing information using general behavioral \
rules, invariants, or input-output relationships.
  3. Be precise enough for an LLM to generate correct code.
  4. Preserve all existing correct information.

Keep the documentation DETAILED and contract-complete — preserve (and improve) \
the structured sections: **<name>** one-line purpose, **Signature** (exact \
return type, name, and every parameter with its type), **Parameters** (one \
`- name (type): ...` bullet each), a thorough step-by-step **Behavior** \
(algorithm, branches, edge cases, side effects), and **Returns**. Use ONLY \
`**bold**` labels and `-` bullets — no Markdown '#' headings, no '---' \
dividers, no code fences.

Critical Constraint:
Do NOT hard-code specific test input values or expected output values from \
the failures into the documentation. The refined documentation must \
describe the entity's general behavior, not memorize the particular test \
cases used during the search.

Output:
Provide only the refined documentation, without any explanation.
"""


TEMPLATES: dict[str, str] = {
    "diagnosis": DIAGNOSIS,
    "prescription": PRESCRIPTION,
}


def render(name: str, **kwargs: Any) -> str:
    """Render a named template with the given keyword arguments.

    Raises ``KeyError`` if the template name is unknown or any required
    placeholder is missing.
    """
    if name not in TEMPLATES:
        raise KeyError(
            f"unknown template '{name}'; available: {sorted(TEMPLATES)}"
        )
    return TEMPLATES[name].format(**kwargs)
