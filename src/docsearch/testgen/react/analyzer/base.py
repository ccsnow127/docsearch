"""Abstract base class for language adapters."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from ..models import (
    FunctionInfo,
    DependencyInfo,
    TestCase,
    TestResult,
    Coverage,
    Language,
)


class LanguageAdapter(ABC):
    """Abstract base class for language-specific adapters.

    Each language adapter handles:
    - Parsing source code to extract functions/methods
    - Identifying dependencies that need mocking
    - Running tests and measuring coverage
    - Generating complete test files
    """

    @property
    @abstractmethod
    def language(self) -> Language:
        """Return the language this adapter handles."""
        pass

    @abstractmethod
    def extract_functions(self, source_code: str) -> list[FunctionInfo]:
        """Extract public functions and methods from source code.

        Args:
            source_code: The source code to analyze.

        Returns:
            List of FunctionInfo objects for testable functions.
        """
        pass

    @abstractmethod
    def get_imports(self, source_code: str) -> list[str]:
        """Get required import statements from source code.

        Args:
            source_code: The source code to analyze.

        Returns:
            List of import statements.
        """
        pass

    @abstractmethod
    def get_constructors(self, source_code: str) -> list[str]:
        """Get available constructor signatures for classes.

        Args:
            source_code: The source code to analyze.

        Returns:
            List of constructor signatures.
        """
        pass

    @abstractmethod
    def identify_external_dependencies(
        self, source_code: str
    ) -> list[DependencyInfo]:
        """Identify external dependencies that should be mocked.

        Only external dependencies (DB, network, filesystem, time, random)
        should be mocked. Internal module calls should NOT be mocked.

        Args:
            source_code: The source code to analyze.

        Returns:
            List of DependencyInfo objects for mockable dependencies.
        """
        pass

    @abstractmethod
    def check_syntax(self, code: str) -> tuple[bool, Optional[str]]:
        """Check if code has valid syntax.

        Args:
            code: The code to check.

        Returns:
            Tuple of (is_valid, error_message).
        """
        pass

    @abstractmethod
    def run_tests(
        self,
        test_file: Path,
        source_file: Path,
        timeout: int = 60,
    ) -> TestResult:
        """Execute tests and return results.

        Args:
            test_file: Path to the test file.
            source_file: Path to the source file being tested.
            timeout: Timeout in seconds.

        Returns:
            TestResult with pass/fail counts and output.
        """
        pass

    @abstractmethod
    def measure_coverage(
        self,
        test_file: Path,
        source_file: Path,
        timeout: int = 60,
    ) -> tuple[Coverage, TestResult]:
        """Run tests and measure coverage.

        Args:
            test_file: Path to the test file.
            source_file: Path to the source file being tested.
            timeout: Timeout in seconds.

        Returns:
            Tuple of (Coverage metrics, TestResult with pass/fail/error info).
        """
        pass

    @abstractmethod
    def generate_test_file(
        self,
        test_cases: list[TestCase],
        source_file: Path,
        imports: list[str],
    ) -> str:
        """Generate a complete test file from test cases.

        Args:
            test_cases: List of test cases to include.
            source_file: Path to the source file being tested.
            imports: Required import statements.

        Returns:
            Complete test file content as a string.
        """
        pass

    def get_test_file_extension(self) -> str:
        """Get the file extension for test files."""
        if self.language == Language.PYTHON:
            return ".py"
        elif self.language == Language.JAVA:
            return ".java"
        return ".txt"

    def get_test_file_name(self, source_file: Path) -> str:
        """Generate appropriate test file name for the source file."""
        stem = source_file.stem
        if self.language == Language.PYTHON:
            return f"test_{stem}.py"
        elif self.language == Language.JAVA:
            return f"{stem}Test.java"
        return f"test_{stem}{self.get_test_file_extension()}"
