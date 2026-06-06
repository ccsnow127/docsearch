"""LLM-based test case generation."""

from docsearch.testgen.coverage_loop import (
    TestGenConfig,
    TestGenResult,
    generate_tests_for_entity,
)
from docsearch.testgen.external_deps import ExternalDeps, detect_external_deps
from docsearch.testgen.extract import extract_tests, normalize_test
from docsearch.testgen.filters import deduplicate, filter_direct, references_entity
from docsearch.testgen.orchestrator import (
    ModuleTestGenResult,
    generate_module_tests,
)
from docsearch.testgen.validator import validate_tests_against_reference

__all__ = [
    "TestGenConfig",
    "TestGenResult",
    "ModuleTestGenResult",
    "generate_tests_for_entity",
    "generate_module_tests",
    "ExternalDeps",
    "detect_external_deps",
    "extract_tests",
    "normalize_test",
    "deduplicate",
    "filter_direct",
    "references_entity",
    "validate_tests_against_reference",
]
