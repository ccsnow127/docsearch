"""Python language adapter using ast, pytest, and coverage.py."""

import ast
import subprocess
import sys
import tempfile
import re
from pathlib import Path
from typing import Optional

from .base import LanguageAdapter
from ..models import (
    FunctionInfo,
    DependencyInfo,
    TestCase,
    TestResult,
    Coverage,
    Language,
)


# External dependencies that should be mocked
EXTERNAL_DEPENDENCIES = {
    # Database
    "sqlite3", "psycopg2", "pymysql", "sqlalchemy", "pymongo", "redis",
    # Network
    "requests", "urllib", "urllib3", "httpx", "aiohttp", "socket",
    # Filesystem
    "os.path", "pathlib", "shutil", "glob", "fnmatch",
    # Time
    "time.sleep", "time.time", "datetime.datetime.now", "datetime.date.today",
    # Random
    "random",
    # Other I/O
    "subprocess", "multiprocessing", "threading",
}

# Patterns indicating file I/O
FILE_IO_PATTERNS = {
    "open(", "read(", "write(", "Path(", ".read_text(", ".write_text(",
    ".mkdir(", ".rmdir(", ".unlink(", "os.remove", "os.makedirs",
}


class PythonAdapter(LanguageAdapter):
    """Python language adapter using ast, pytest, and coverage.py."""

    @property
    def language(self) -> Language:
        return Language.PYTHON

    def extract_functions(self, source_code: str) -> list[FunctionInfo]:
        """Extract public functions and methods from Python source code."""
        functions = []
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return functions

        source_lines = source_code.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                # Skip private functions (except __init__)
                if node.name.startswith("_") and node.name != "__init__":
                    continue

                # Determine if this is a method
                class_name = None
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.ClassDef):
                        for child in ast.iter_child_nodes(parent):
                            if child is node:
                                class_name = parent.name
                                break

                # Extract function info
                func_info = self._extract_function_info(
                    node, source_code, source_lines, class_name
                )
                functions.append(func_info)

        return functions

    def _extract_function_info(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        source_code: str,
        source_lines: list[str],
        class_name: Optional[str],
    ) -> FunctionInfo:
        """Extract FunctionInfo from an AST function node."""
        # Get signature
        signature = self._get_signature(node)

        # Get body
        body_lines = source_lines[node.lineno - 1 : node.end_lineno]
        body = "\n".join(body_lines)

        # Get docstring
        docstring = ast.get_docstring(node)

        # Get parameter types from annotations
        param_types = {}
        for arg in node.args.args:
            if arg.annotation:
                param_types[arg.arg] = ast.unparse(arg.annotation)

        # Get return type
        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns)

        return FunctionInfo(
            name=node.name,
            signature=signature,
            body=body,
            docstring=docstring,
            is_public=not node.name.startswith("_") or node.name == "__init__",
            class_name=class_name,
            param_types=param_types,
            return_type=return_type,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
        )

    def _get_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Get function signature as a string."""
        args = []

        # Regular args
        for i, arg in enumerate(node.args.args):
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {ast.unparse(arg.annotation)}"

            # Check for default value
            default_offset = len(node.args.args) - len(node.args.defaults)
            if i >= default_offset:
                default = node.args.defaults[i - default_offset]
                arg_str += f" = {ast.unparse(default)}"

            args.append(arg_str)

        # *args
        if node.args.vararg:
            vararg_str = f"*{node.args.vararg.arg}"
            if node.args.vararg.annotation:
                vararg_str += f": {ast.unparse(node.args.vararg.annotation)}"
            args.append(vararg_str)

        # **kwargs
        if node.args.kwarg:
            kwarg_str = f"**{node.args.kwarg.arg}"
            if node.args.kwarg.annotation:
                kwarg_str += f": {ast.unparse(node.args.kwarg.annotation)}"
            args.append(kwarg_str)

        signature = f"def {node.name}({', '.join(args)})"
        if node.returns:
            signature += f" -> {ast.unparse(node.returns)}"

        return signature

    def get_imports(self, source_code: str) -> list[str]:
        """Get import statements from Python source code."""
        imports = []
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return imports

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        imports.append(f"import {alias.name} as {alias.asname}")
                    else:
                        imports.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = ", ".join(
                    f"{alias.name} as {alias.asname}" if alias.asname else alias.name
                    for alias in node.names
                )
                imports.append(f"from {module} import {names}")

        return imports

    def get_constructors(self, source_code: str) -> list[str]:
        """Get constructor signatures for classes in the source code."""
        constructors = []
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return constructors

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        # Get parameters (excluding self)
                        params = []
                        for arg in item.args.args[1:]:  # Skip self
                            param_str = arg.arg
                            if arg.annotation:
                                param_str += f": {ast.unparse(arg.annotation)}"
                            params.append(param_str)
                        constructors.append(f"{node.name}({', '.join(params)})")
                        break
                else:
                    # No __init__ found, default constructor
                    constructors.append(f"{node.name}()")

        return constructors

    def identify_external_dependencies(
        self, source_code: str
    ) -> list[DependencyInfo]:
        """Identify external dependencies that should be mocked."""
        dependencies = []
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return dependencies

        imported_modules = set()

        # Collect imported modules
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_modules.add(node.module.split(".")[0])

        # Check for external dependencies
        for module in imported_modules:
            if module in EXTERNAL_DEPENDENCIES or any(
                module.startswith(ext.split(".")[0]) for ext in EXTERNAL_DEPENDENCIES
            ):
                dep_type = self._categorize_dependency(module)
                dependencies.append(
                    DependencyInfo(
                        name=module,
                        type=dep_type,
                        is_external=True,
                        needs_mock=True,
                        module_path=module,
                    )
                )

        # Check for file I/O patterns in code
        if any(pattern in source_code for pattern in FILE_IO_PATTERNS):
            if not any(d.type == "filesystem" for d in dependencies):
                dependencies.append(
                    DependencyInfo(
                        name="file_io",
                        type="filesystem",
                        is_external=True,
                        needs_mock=True,
                    )
                )

        return dependencies

    def _categorize_dependency(self, module: str) -> str:
        """Categorize a dependency by type."""
        database_modules = {"sqlite3", "psycopg2", "pymysql", "sqlalchemy", "pymongo", "redis"}
        network_modules = {"requests", "urllib", "urllib3", "httpx", "aiohttp", "socket"}
        time_modules = {"time", "datetime"}
        random_modules = {"random"}

        if module in database_modules:
            return "database"
        elif module in network_modules:
            return "network"
        elif module in time_modules:
            return "time"
        elif module in random_modules:
            return "random"
        else:
            return "filesystem"

    def check_syntax(self, code: str) -> tuple[bool, Optional[str]]:
        """Check if Python code has valid syntax."""
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"Syntax error at line {e.lineno}: {e.msg}"

    def run_tests(
        self,
        test_file: Path,
        source_file: Path,
        timeout: int = 60,
    ) -> TestResult:
        """Run pytest on the test file."""
        try:
            # Resolve to absolute paths
            source_file = source_file.resolve()
            test_file = test_file.resolve()

            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=source_file.parent,
                env={**subprocess.os.environ, "PYTHONPATH": str(source_file.parent)},
            )

            output = result.stdout + result.stderr

            # Parse pytest output
            passed = failed = errors = 0

            # Look for summary line like "5 passed, 2 failed"
            summary_match = re.search(
                r"(\d+) passed(?:.*?(\d+) failed)?(?:.*?(\d+) error)?",
                output,
            )
            if summary_match:
                passed = int(summary_match.group(1) or 0)
                failed = int(summary_match.group(2) or 0)
                errors = int(summary_match.group(3) or 0)

            # Extract failure details
            failure_details = []
            failure_sections = re.findall(
                r"FAILED (.*?) - (.*?)(?=\n(?:FAILED|PASSED|=|$))",
                output,
                re.DOTALL,
            )
            for test_name, reason in failure_sections:
                failure_details.append({"test": test_name.strip(), "reason": reason.strip()})

            return TestResult(
                passed=passed,
                failed=failed,
                errors=errors,
                output=output,
                failure_details=failure_details,
            )

        except subprocess.TimeoutExpired:
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                output="Test execution timed out",
                failure_details=[{"test": "all", "reason": "Timeout"}],
            )
        except Exception as e:
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                output=str(e),
                failure_details=[{"test": "all", "reason": str(e)}],
            )

    def measure_coverage(
        self,
        test_file: Path,
        source_file: Path,
        timeout: int = 60,
    ) -> tuple[Coverage, TestResult]:
        """Run tests with coverage measurement.

        Returns:
            Tuple of (Coverage, TestResult).
        """
        try:
            # Resolve to absolute paths for coverage to work correctly
            source_file = source_file.resolve()
            test_file = test_file.resolve()

            # Run coverage
            with tempfile.NamedTemporaryFile(suffix=".coverage", delete=False) as cov_file:
                cov_path = cov_file.name

            env = {
                **subprocess.os.environ,
                "PYTHONPATH": str(source_file.parent),
                "COVERAGE_FILE": cov_path,
            }

            # Run pytest with coverage
            test_result = subprocess.run(
                [
                    sys.executable, "-m", "coverage", "run",
                    "--source", str(source_file.parent),
                    "--branch",
                    "-m", "pytest", str(test_file), "-v", "--tb=short",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=source_file.parent,
                env=env,
            )

            # Parse test results
            test_output = test_result.stdout + test_result.stderr
            passed = failed = errors = 0
            failure_details = []

            summary_match = re.search(
                r"(\d+) passed(?:.*?(\d+) failed)?(?:.*?(\d+) error)?",
                test_output,
            )
            if summary_match:
                passed = int(summary_match.group(1) or 0)
                failed = int(summary_match.group(2) or 0)
                errors = int(summary_match.group(3) or 0)

            # Check for syntax/import errors
            if "SyntaxError" in test_output or "ImportError" in test_output:
                errors = max(errors, 1)
                failure_details.append({
                    "type": "SyntaxError",
                    "message": test_output[:500],
                })

            test_result_obj = TestResult(
                passed=passed,
                failed=failed,
                errors=errors,
                output=test_output,
                failure_details=failure_details,
            )

            # Get coverage report
            result = subprocess.run(
                [sys.executable, "-m", "coverage", "report", "--show-missing"],
                capture_output=True,
                text=True,
                cwd=source_file.parent,
                env=env,
            )

            # Also get JSON report for detailed info
            json_result = subprocess.run(
                [sys.executable, "-m", "coverage", "json", "-o", "-"],
                capture_output=True,
                text=True,
                cwd=source_file.parent,
                env=env,
            )

            coverage = self._parse_coverage_output(
                result.stdout, json_result.stdout, source_file
            )
            return coverage, test_result_obj

        except subprocess.TimeoutExpired:
            error_result = TestResult(
                passed=0,
                failed=0,
                errors=1,
                output="Test execution timed out",
            )
            return Coverage(), error_result
        except Exception as e:
            error_result = TestResult(
                passed=0,
                failed=0,
                errors=1,
                output=str(e),
            )
            return Coverage(), error_result

    def _parse_coverage_output(
        self, report_output: str, json_output: str, source_file: Path
    ) -> Coverage:
        """Parse coverage report output."""
        import json as json_module

        coverage = Coverage()

        # Try to parse JSON output first (more accurate)
        try:
            data = json_module.loads(json_output)
            source_name = source_file.name

            for file_path, file_data in data.get("files", {}).items():
                if source_name in file_path:
                    summary = file_data.get("summary", {})
                    coverage.total_lines = summary.get("num_statements", 0)
                    coverage.covered_lines = summary.get("covered_lines", 0)
                    coverage.total_branches = summary.get("num_branches", 0)
                    coverage.covered_branches = summary.get("covered_branches", 0)
                    coverage.uncovered_lines = file_data.get("missing_lines", [])

                    if coverage.total_lines > 0:
                        coverage.line = coverage.covered_lines / coverage.total_lines
                    if coverage.total_branches > 0:
                        coverage.branch = coverage.covered_branches / coverage.total_branches

                    break
        except (json_module.JSONDecodeError, KeyError):
            # Fall back to parsing text output
            for line in report_output.splitlines():
                if source_file.name in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        try:
                            coverage.total_lines = int(parts[1])
                            missed = int(parts[2])
                            coverage.covered_lines = coverage.total_lines - missed
                            pct = parts[3].rstrip("%")
                            coverage.line = float(pct) / 100.0
                        except (ValueError, IndexError):
                            pass

                    # Parse missing lines
                    if "Missing" in line or len(parts) > 4:
                        missing_part = parts[-1] if len(parts) > 4 else ""
                        if missing_part:
                            coverage.uncovered_lines = self._parse_line_ranges(missing_part)
                    break

        return coverage

    def _parse_line_ranges(self, ranges_str: str) -> list[int]:
        """Parse line range strings like '10-15, 20, 25-30'."""
        lines = []
        for part in ranges_str.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    start, end = part.split("-")
                    lines.extend(range(int(start), int(end) + 1))
                except ValueError:
                    pass
            else:
                try:
                    lines.append(int(part))
                except ValueError:
                    pass
        return lines

    def generate_test_file(
        self,
        test_cases: list[TestCase],
        source_file: Path,
        imports: list[str],
    ) -> str:
        """Generate a complete pytest test file."""
        module_name = source_file.stem

        lines = [
            '"""Tests for {}.py"""'.format(module_name),
            "",
            "import pytest",
        ]

        # Add imports
        for imp in imports:
            if imp not in lines:
                lines.append(imp)

        # Import the module being tested
        lines.append(f"from {module_name} import *")
        lines.append("")
        lines.append("")

        # Add test cases
        for test_case in test_cases:
            lines.append(test_case.code)
            lines.append("")
            lines.append("")

        return "\n".join(lines).strip() + "\n"
