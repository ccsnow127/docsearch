"""
Test Executor for treesearch - Runs tests against generated code.
"""

import subprocess
import os
import re
import sys
import shutil
import tempfile
from typing import Optional
from pathlib import Path
from dataclasses import dataclass


# Strip ANSI SGR colour codes (e.g. "\x1b[32mPASSED\x1b[0m"). pytest emits these
# whenever a colour-forcing env var is set (FORCE_COLOR / PY_COLORS) even though
# output is captured, which otherwise breaks every "::test_x PASSED" match.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class TestResult:
    """Represents the result of running tests."""
    passed: int
    failed: int
    total: int
    errors: list[str]
    output: str = ""

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.total > 0


class TestExecutor:
    """
    Executes tests against generated code.
    Creates a runner script that patches the target module before tests run.
    """

    # Directory names never mirrored into the eval workspace's repo_sources.
    _SKIP_DIRS = {".git", "target", "build", "out", "__pycache__",
                  ".mvn", ".gradle", "bin", "node_modules", ".tox", ".venv"}

    def __init__(
        self,
        test_suite_path: str,
        target_module: str,
        repo_path: str = ".",
        timeout: int = 60,
        target_rel: Optional[str] = None,
    ):
        """
        Args:
            test_suite_path: Path to the test file
            target_module: Module path (e.g., "stocktrends.indicators")
            repo_path: Path to the repository root
            timeout: Test timeout in seconds
            target_rel: Repo-relative path of the target source file (e.g.
                "pint/util.py"). When set, generated code is evaluated in a
                testgen-style workspace — the code written to ``<source_base>``
                next to a read-only ``repo_sources/`` mirror of the repo and the
                test suite — and pytest runs there. This matches the layout the
                generated tests were authored against (they may load the module
                in-package, e.g. ``pint.util``, to satisfy relative imports),
                instead of the exec-and-monkeypatch runner which cannot handle
                ``from . import`` in the target. Falls back to the runner when
                unset.
        """
        self.test_suite_path = test_suite_path
        self.target_module = target_module
        self.repo_path = Path(repo_path).resolve()
        self.timeout = timeout
        self.target_rel = (target_rel or "").replace("\\", "/").lstrip("/") or None
        self._ws: Optional[str] = None  # cached eval workspace (built once)

    def run(self, generated_code: str, iteration: int = 0) -> TestResult:
        """
        Run tests with the generated code.

        Args:
            generated_code: The generated Python code
            iteration: Current iteration number (for logging)

        Returns:
            TestResult with pass/fail counts and errors
        """
        return self._run_tests(generated_code)

    def _run_tests(self, code: str) -> TestResult:
        """Run the tests with the generated code."""
        # First check for syntax errors
        try:
            compile(code, '<generated>', 'exec')
        except SyntaxError as e:
            return TestResult(
                passed=0,
                failed=1,
                total=1,
                errors=[f"SyntaxError: {e}"],
                output=str(e)
            )

        # Repo-level path: run the suite in a testgen-style workspace so the
        # generated code is loaded the SAME way the test was authored to load it
        # (in-package, with repo_sources reachable). This is what makes targets
        # with relative imports / package-relative tests score a real phi instead
        # of erroring out (phi=0) under the exec-and-monkeypatch runner.
        if self.target_rel:
            return self._run_in_workspace(code)

        # Create a test runner script that patches and runs tests
        runner_script = self._create_runner_script(code)
        test_path = Path(self.test_suite_path).resolve()
        test_dir = test_path.parent
        runner_path = test_dir / "_test_runner_generated.py"

        try:
            with open(runner_path, 'w') as f:
                f.write(runner_script)

            env = os.environ.copy()
            env['PYTHONPATH'] = str(self.repo_path) + ':' + env.get('PYTHONPATH', '')

            result = subprocess.run(
                [sys.executable, str(runner_path)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.repo_path),
                env=env
            )

            return self._parse_pytest_output(result.stdout + result.stderr)

        except subprocess.TimeoutExpired:
            return TestResult(
                passed=0,
                failed=1,
                total=1,
                errors=["Test execution timed out"],
                output="Timeout"
            )
        except Exception as e:
            import traceback
            return TestResult(
                passed=0,
                failed=1,
                total=1,
                errors=[f"Test execution error: {str(e)}", traceback.format_exc()],
                output=str(e)
            )
        finally:
            try:
                if runner_path.exists():
                    os.unlink(runner_path)
            except:
                pass

    def _ensure_workspace(self) -> str:
        """Build (once, then cache) a testgen-style eval workspace:

            <ws>/<test_base>          the generated test suite
            <ws>/repo_sources/<rel>   a read-only mirror of the repo's .py files
                                      (minus the target file and test trees)

        The generated target source itself is (re)written per-evaluation by
        :meth:`_run_in_workspace`. repo_sources lets tests that load the module
        in-package reach the rest of the repo; package deps also resolve from the
        editable install when present.
        """
        if self._ws and os.path.isdir(self._ws):
            return self._ws
        ws = tempfile.mkdtemp(prefix="dsx_eval_")
        root = str(self.repo_path)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d not in self._SKIP_DIRS and d.lower() not in ("test", "tests")
            ]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root).replace("\\", "/")
                # NOTE: unlike the codegen agent's workspace, the eval workspace
                # INCLUDES the target file in repo_sources (matching testgen's
                # layout). The generated tests load the package (`import pint`)
                # whose __init__ does `from .util import ...`, so repo_sources
                # must contain the real submodule; the fixture then OVERRIDES
                # sys.modules with the generated code loaded from <source_base>.
                # There is no anti-cheat concern here — the evaluator only RUNS
                # tests, it never reconstructs code.
                dest = os.path.join(ws, "repo_sources", rel)
                os.makedirs(os.path.dirname(dest) or ws, exist_ok=True)
                try:
                    shutil.copy(full, dest)
                except OSError:
                    pass
        # The test suite lives at the workspace root (where the generated tests
        # expect it — they resolve repo_sources/<source_base> relative to it).
        try:
            shutil.copy(self.test_suite_path,
                        os.path.join(ws, os.path.basename(self.test_suite_path)))
        except OSError:
            pass
        self._ws = ws
        return ws

    def _run_in_workspace(self, code: str) -> TestResult:
        """Write generated code as the target source and run pytest in-workspace."""
        ws = self._ensure_workspace()
        source_base = os.path.basename(self.target_rel)
        with open(os.path.join(ws, source_base), "w", encoding="utf-8") as f:
            f.write(code)
        # Drop stale bytecode so the freshly written source is what gets imported.
        for pyc in Path(ws).rglob("__pycache__"):
            shutil.rmtree(pyc, ignore_errors=True)

        # Only the workspace root goes on PYTHONPATH (so the generated
        # <source_base> imports as a top-level module when the test does a flat
        # `import <stem>`). repo_sources is deliberately NOT added globally: the
        # generated tests that need it insert it themselves, in the right order
        # (e.g. pint's fixture loads the module as `pint.util` BEFORE `import
        # pint` pulls submodules) — adding it here would import the package at
        # collection time and break that ordering. Cross-package deps resolve
        # from the editable install (`pip install -e`).
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([ws, env.get("PYTHONPATH", "")])
        test_base = os.path.basename(self.test_suite_path)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_base,
                 "-v", "--tb=short", "-p", "no:cacheprovider"],
                capture_output=True, text=True, timeout=self.timeout,
                cwd=ws, env=env,
            )
        except subprocess.TimeoutExpired:
            return TestResult(passed=0, failed=1, total=1,
                              errors=["Test execution timed out"], output="Timeout")
        return self._parse_pytest_output(result.stdout + result.stderr)

    def __del__(self):
        try:
            if self._ws and os.path.isdir(self._ws):
                shutil.rmtree(self._ws, ignore_errors=True)
        except Exception:
            pass

    def _create_runner_script(self, code: str) -> str:
        """Create a test runner script that replaces generated classes and runs pytest."""
        escaped_code = code.replace('\\', '\\\\').replace("'''", "\\'\\'\\'")
        abs_test_path = Path(self.test_suite_path).resolve()

        return f'''#!/usr/bin/env python
# Auto-generated test runner - replaces ALL generated classes in module and submodules
import sys
sys.path.insert(0, "{self.repo_path}")

import importlib
import pkgutil
import pandas as pd
import numpy as np
from datetime import datetime
from uuid import UUID
from typing import Optional, List, Dict, Any, Union, Tuple, Set, Callable, Literal
from collections import OrderedDict, defaultdict, namedtuple

# Import the target module
module = importlib.import_module("{self.target_module}")

# The generated code
generated_code = \'\'\'
{escaped_code}
\'\'\'

# Create namespace with necessary imports
namespace = {{
    "pd": pd,
    "np": np,
    "datetime": datetime,
    "UUID": UUID,
    "Optional": Optional,
    "List": List,
    "Dict": Dict,
    "Any": Any,
    "Union": Union,
    "Tuple": Tuple,
    "Set": Set,
    "Callable": Callable,
    "Literal": Literal,
    "OrderedDict": OrderedDict,
    "defaultdict": defaultdict,
    "namedtuple": namedtuple,
}}

# Execute the code to define the classes
try:
    exec(generated_code, namespace)
except Exception as e:
    print(f"Error executing generated code: {{e}}")
    sys.exit(1)

# Collect all classes and functions from generated code
generated_items = {{}}
for name, obj in namespace.items():
    if isinstance(obj, type) or callable(obj):
        if not name.startswith('_') and name not in ['pd', 'np', 'datetime', 'UUID', 'Optional', 'List', 'Dict', 'Any', 'Union', 'Tuple', 'Set', 'Callable', 'Literal', 'OrderedDict', 'defaultdict', 'namedtuple']:
            generated_items[name] = obj

if not generated_items:
    print("No classes or functions found in generated code")
    print(f"Available names: {{list(namespace.keys())}}")
    sys.exit(1)

# Replace in main module
items_replaced = []
for name, obj in generated_items.items():
    if hasattr(module, name):
        setattr(module, name, obj)
        items_replaced.append(f"{{name}} (main)")

# Also replace in all submodules (for packages like aecg with aecg.models, aecg.utils, etc.)
try:
    if hasattr(module, '__path__'):
        # It's a package, iterate through submodules
        for importer, modname, ispkg in pkgutil.iter_modules(module.__path__, module.__name__ + '.'):
            try:
                submodule = importlib.import_module(modname)
                for name, obj in generated_items.items():
                    if hasattr(submodule, name):
                        setattr(submodule, name, obj)
                        items_replaced.append(f"{{name}} ({{modname}})")
            except ImportError as e:
                print(f"Warning: Could not import submodule {{modname}}: {{e}}")
except Exception as e:
    print(f"Warning: Error while patching submodules: {{e}}")

print(f"Replaced items: {{items_replaced}}")

# Now run pytest
import pytest
sys.exit(pytest.main([
    "{abs_test_path}",
    "-v",
    "--tb=short",
    "-p", "no:cacheprovider",
]))
'''

    def _parse_pytest_output(self, output: str) -> TestResult:
        """Parse pytest output to extract test results."""
        # Drop colour codes up front so the captured text is parseable (and so
        # the stored .output the evaluator scans is clean) regardless of the
        # ambient FORCE_COLOR/PY_COLORS environment.
        output = _ANSI_RE.sub("", output)
        passed = 0
        failed = 0
        errors = []

        passed_match = re.search(r'(\d+) passed', output)
        failed_match = re.search(r'(\d+) failed', output)
        error_match = re.search(r'(\d+) error', output)

        if passed_match:
            passed = int(passed_match.group(1))
        if failed_match:
            failed = int(failed_match.group(1))
        if error_match:
            failed += int(error_match.group(1))

        total = passed + failed

        lines = output.split('\n')
        seen_errors = set()
        exception_errors = []
        failed_tests = []
        current_test = None  # Track current test for associating errors

        for line in lines:
            stripped = line.strip()

            # Capture FAILED test names and track current test
            if 'FAILED' in line and '::' in line:
                failed_tests.append(stripped)
                test_match = re.search(r'::(test_\w+)', line)
                if test_match:
                    current_test = test_match.group(1)

            # Also track test names in FAILURES section headers (e.g., "_____ TestPnF.test_PnF_get_bar_ohlc_data_1 _____")
            elif '_____' in line and 'test_' in line:
                test_match = re.search(r'(test_\w+)', line)
                if test_match:
                    current_test = test_match.group(1)

            # Capture pytest error lines (prefixed with "E   ")
            elif line.startswith('E   ') or line.startswith('E\t'):
                error_msg = line[1:].strip()
                if error_msg and error_msg not in seen_errors:
                    if 'Target:' not in error_msg and current_test:
                        entity = self._test_name_to_entity(current_test)
                        if entity:
                            error_msg = f"Target: {entity} | {error_msg}"
                    exception_errors.append(error_msg)
                    seen_errors.add(error_msg)

            # Capture specific error types
            elif any(err_type in stripped for err_type in [
                'AttributeError:', 'TypeError:', 'ValueError:',
                'KeyError:', 'IndexError:', 'NameError:',
                'AssertionError:', 'RuntimeError:', 'ImportError:',
                'SyntaxError:', 'ModuleNotFoundError:'
            ]):
                if stripped not in seen_errors:
                    if 'Target:' not in stripped and current_test:
                        entity = self._test_name_to_entity(current_test)
                        if entity:
                            stripped = f"Target: {entity} | {stripped}"
                    exception_errors.append(stripped)
                    seen_errors.add(stripped)

        errors = exception_errors[:15]

        if not errors and failed_tests:
            errors.append(f"{len(failed_tests)} tests failed (check test output for details)")

        if total == 0 and output.strip():
            if 'SyntaxError' in output or 'ImportError' in output:
                errors.append("Code has syntax or import errors")
                failed = 1
                total = 1
            elif 'collected 0 items' in output:
                errors.append("No tests collected")
                failed = 1
                total = 1

        return TestResult(
            passed=passed,
            failed=failed,
            total=total,
            errors=errors,
            output=output
        )

    def _test_name_to_entity(self, test_name: str) -> Optional[str]:
        """
        Convert test name to entity name.

        Supports two patterns:
        1. PascalCase: test_ClassName_method_name_id -> ClassName.method_name
           Examples:
               test_PnF_get_bar_ohlc_data_1 -> PnF.get_bar_ohlc_data
               test_Renko_period_close_bricks_1 -> Renko.period_close_bricks

        2. lowercase: test_function_name_* -> function_name
           Examples:
               test_decode_simple_object -> decode
               test_compute_depth_strict -> compute_depth
        """
        if not test_name.startswith("test_"):
            return None

        parts = test_name[5:].split('_')
        if not parts:
            return None

        # Pattern 1: Find class name (first part starting with uppercase)
        class_name = None
        method_start_idx = None

        for i, part in enumerate(parts):
            if part and part[0].isupper():
                class_name = part
                method_start_idx = i + 1
                break

        if class_name and method_start_idx is not None:
            # Get method parts, exclude trailing numeric id
            method_parts = parts[method_start_idx:]
            if method_parts and method_parts[-1].isdigit():
                method_parts = method_parts[:-1]

            if not method_parts:
                return class_name

            return f"{class_name}.{'_'.join(method_parts)}"

        # Pattern 2: No PascalCase found, join all parts as entity name (lowercase function)
        # Remove trailing numeric id, join remaining parts
        # e.g., test_parse_primitive_1 -> parse_primitive
        # e.g., test_compute_depth_6 -> compute_depth
        if parts:
            # Remove trailing numeric id
            if parts[-1].isdigit():
                parts = parts[:-1]
            if parts:
                return '_'.join(parts)

        return None
