"""Data models for the Test Generator module."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TestType(Enum):
    """Type of test case."""
    NORMAL = "normal"
    BOUNDARY = "boundary"
    ERROR = "error"


class Language(Enum):
    """Supported programming languages."""
    PYTHON = "python"
    JAVA = "java"


@dataclass
class FunctionInfo:
    """Information about a function or method to test.

    Attributes:
        name: Function/method name.
        signature: Full function signature.
        body: Function body code.
        docstring: Function docstring if available.
        is_public: Whether the function is public.
        class_name: Name of containing class (if method).
        param_types: Dictionary mapping parameter names to types.
        return_type: Return type annotation if available.
        start_line: Starting line number in source.
        end_line: Ending line number in source.
    """
    name: str
    signature: str
    body: str
    docstring: Optional[str] = None
    is_public: bool = True
    class_name: Optional[str] = None
    param_types: dict[str, str] = field(default_factory=dict)
    return_type: Optional[str] = None
    start_line: int = 0
    end_line: int = 0


@dataclass
class DependencyInfo:
    """Information about a dependency that may need mocking.

    Attributes:
        name: Dependency name.
        type: Type of dependency (e.g., 'database', 'network', 'filesystem').
        is_external: Whether this is an external dependency.
        needs_mock: Whether this dependency should be mocked.
        module_path: Import path for the dependency.
    """
    name: str
    type: str
    is_external: bool = False
    needs_mock: bool = False
    module_path: Optional[str] = None


@dataclass
class TestContext:
    """Context needed for generating tests for a function.

    Attributes:
        function: The function to test.
        imports: Required import statements.
        constructors: Available constructors for test setup.
        helper_methods: Helper methods that might be useful.
        dependencies: Dependencies that may need mocking.
        source_code: Full source code for context.
    """
    function: FunctionInfo
    imports: list[str] = field(default_factory=list)
    constructors: list[str] = field(default_factory=list)
    helper_methods: list[str] = field(default_factory=list)
    dependencies: list[DependencyInfo] = field(default_factory=list)
    source_code: str = ""


@dataclass
class TestCase:
    """A single test case.

    Attributes:
        name: Test function/method name.
        function_name: Name of function being tested.
        code: Complete test code.
        inputs: Description of test inputs.
        test_type: Type of test (normal, boundary, error).
        description: Human-readable description.
    """
    name: str
    function_name: str
    code: str
    inputs: str = ""
    test_type: TestType = TestType.NORMAL
    description: str = ""


@dataclass
class Coverage:
    """Coverage metrics for a test suite.

    Attributes:
        line: Line coverage as a ratio (0.0 to 1.0).
        branch: Branch coverage as a ratio (0.0 to 1.0).
        uncovered_lines: List of line numbers not covered.
        uncovered_branches: List of uncovered branch descriptions.
        total_lines: Total number of executable lines.
        covered_lines: Number of covered lines.
        total_branches: Total number of branches.
        covered_branches: Number of covered branches.
    """
    line: float = 0.0
    branch: float = 0.0
    uncovered_lines: list[int] = field(default_factory=list)
    uncovered_branches: list[str] = field(default_factory=list)
    total_lines: int = 0
    covered_lines: int = 0
    total_branches: int = 0
    covered_branches: int = 0
    # Per-method coverage: list of {"class": "Renko", "method": "periodCloseBricks",
    #   "covered": 22, "total": 55, "pct": 0.40}
    # Sorted by pct ascending (lowest coverage first)
    method_coverage: list[dict] = field(default_factory=list)

    def meets_threshold(self, line_threshold: float, branch_threshold: float) -> bool:
        """Check if coverage meets the specified thresholds."""
        return self.line >= line_threshold and self.branch >= branch_threshold


@dataclass
class TestResult:
    """Result of running tests.

    Attributes:
        passed: Number of passing tests.
        failed: Number of failing tests.
        errors: Number of tests with errors.
        output: Raw test output.
        failure_details: Details about failures.
    """
    passed: int = 0
    failed: int = 0
    errors: int = 0
    output: str = ""
    failure_details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Total number of tests."""
        return self.passed + self.failed + self.errors

    @property
    def success(self) -> bool:
        """Whether all tests passed."""
        return self.failed == 0 and self.errors == 0


@dataclass
class GenerationMetadata:
    """Metadata about the test generation process.

    Attributes:
        iterations: Number of coverage feedback iterations.
        initial_coverage: Coverage before feedback loop.
        final_coverage: Coverage after feedback loop.
        tests_generated: Total tests generated.
        tests_discarded: Tests discarded due to errors.
        fix_attempts: Total fix attempts made.
        llm_calls: Number of LLM API calls.
        stagnant_rounds: Number of consecutive stagnant coverage rounds.
    """
    iterations: int = 0
    initial_coverage: Optional[Coverage] = None
    final_coverage: Optional[Coverage] = None
    tests_generated: int = 0
    tests_discarded: int = 0
    fix_attempts: int = 0
    llm_calls: int = 0
    stagnant_rounds: int = 0


@dataclass
class TestSuite:
    """A complete test suite for a module.

    Attributes:
        module_name: Name of the module being tested.
        language: Programming language.
        test_file_content: Complete generated test file content.
        test_cases: Individual test cases.
        coverage: Coverage metrics.
        generation_metadata: Metadata about the generation process.
        source_file: Path to the source file.
        test_file_path: Path where test file should be written.
    """
    module_name: str
    language: Language
    test_file_content: str
    test_cases: list[TestCase] = field(default_factory=list)
    coverage: Optional[Coverage] = None
    generation_metadata: Optional[GenerationMetadata] = None
    source_file: str = ""
    test_file_path: str = ""
