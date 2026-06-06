"""LLM prompt templates.

Each template is a ``str.format``-style string. Use :func:`render` to
fill in placeholders; missing keys raise ``KeyError``.
"""
from __future__ import annotations

from typing import Any


DIAGNOSIS = """\
You are analyzing test failures to diagnose why an LLM failed to generate \
correct code from a given documentation.

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
You are refining documentation for a code entity based on a diagnosis of \
test failures.

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

Critical Constraint:
Do NOT hard-code specific test input values or expected output values from \
the failures into the documentation. The refined documentation must \
describe the entity's general behavior, not memorize the particular test \
cases used during the search.

Output:
Provide only the refined documentation, without any explanation.
"""


CODE_GENERATION = """\
Generate Python code for all entities in this module based on their \
documentation.

Module: {module_name}

Documentation:
{all_entity_documentation}

Requirements:
- Implement each entity exactly according to its documentation
- Ensure all cross-entity calls are consistent
- Do not add functionality not specified in the documentation

Output:
Provide the complete Python implementation for all entities, without any \
explanation or markdown.
"""


TEST_GENERATION = """\
You are generating pytest-style test functions for a code entity. Each test \
must be a complete, self-contained function with concrete inputs and \
assertions.

Entity Information:
- Name: {entity_name}
- Type: {entity_type}
- Signature: {signature}
- Source Code:
{source_code}

Dependencies:
The following entities are called by this entity:
{dependency_signatures}

Coverage Feedback (uncovered lines):
{uncovered_lines}

External Dependencies Detected:
{external_deps}

Task:
Generate diverse pytest test functions that cover:
  1. Normal cases: typical usage scenarios
  2. Edge cases: boundary conditions, empty inputs, single elements
  3. Corner cases: special values, type boundaries
  4. Targeted cases: inputs that exercise the listed uncovered lines

Requirements:
- Each test must be a complete `def test_*():` function with concrete \
inputs and at least one `assert` statement
- Include informative assertion messages where possible \
(e.g., `assert x == y, f"Expected {{y}} got {{x}}"`)
- For any detected external dependency, isolate it with a pytest fixture \
(mock filesystem/network, freeze time, seed randomness)
- Each test must directly exercise the target entity, not reach it only \
through unrelated callers

Output:
Provide a Python module containing only the test functions and any \
required fixtures, without any explanation or markdown.
"""


TEMPLATES: dict[str, str] = {
    "diagnosis": DIAGNOSIS,
    "prescription": PRESCRIPTION,
    "code_generation": CODE_GENERATION,
    "test_generation": TEST_GENERATION,
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
