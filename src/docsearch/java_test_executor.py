"""
Java Test Executor for DocSearch - Runs JUnit tests against generated Java code.
"""

import csv
import logging
import os
import re
import subprocess
import tempfile
import shutil
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Represents the result of running tests."""
    passed: int = 0
    failed: int = 0
    total: int = 0
    errors: list[str] = field(default_factory=list)
    output: str = ""
    compile_error: Optional[str] = None
    runtime_error: Optional[str] = None
    # JaCoCo line/branch coverage of the TARGET class (filled only when
    # ``run(..., measure_coverage=True)``). ``covered_lines`` total > 0 means
    # coverage was actually measured.
    line_rate: float = 0.0
    branch_rate: float = 0.0
    covered_lines: int = 0
    total_lines: int = 0

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.total > 0


class JavaTestExecutor:
    """
    Executes JUnit tests against generated Java code.
    Creates temp directory, compiles code with javac, runs tests with JUnit Console Launcher.
    """

    # JUnit dependencies - these need to be in the classpath
    JUNIT_JARS = [
        "junit-jupiter-api-5.9.0.jar",
        "junit-jupiter-engine-5.9.0.jar",
        "junit-platform-launcher-1.9.0.jar",
        "junit-platform-engine-1.9.0.jar",
        "junit-platform-commons-1.9.0.jar",
        "opentest4j-1.2.0.jar",
        "apiguardian-api-1.1.2.jar",
        "junit-platform-console-standalone-1.9.0.jar",
    ]

    # Default JDK path
    DEFAULT_JDK_PATH = "/usr/lib/jvm/jdk-11.0.0.1"

    def __init__(
        self,
        test_suite_path: str,
        target_module: str = "Indicators",
        repo_path: str = ".",
        timeout: int = 120,
        java_home: Optional[str] = None,
        junit_lib_path: Optional[str] = None,
        dependency_classpath: str = "",
        target_package: str = "",
        entities: Optional[list] = None,
        target_class: str = "",
    ):
        """
        Args:
            test_suite_path: Path to the JUnit test file (.java)
            target_module: Name of the module being tested (e.g., "Indicators")
            repo_path: Path to the repository root
            timeout: Test timeout in seconds
            java_home: Path to Java installation. If None, uses JAVA_HOME env var.
            junit_lib_path: Path to directory containing JUnit JARs.
            dependency_classpath: The closure ``deps_classpath`` (ground-truth
                classes dir + external jars) to compile/run the generated target
                against. Empty keeps the self-contained single-file behavior.
            target_package: Java package of the target file (e.g.
                "org.jsoup.select"). When set, the generated target and test are
                written under their package directory inside the build dir so
                javac/JUnit see package-structured classes. Empty means the
                default (unnamed) package.
        """
        self.test_suite_path = Path(test_suite_path)
        self.target_module = target_module
        self.repo_path = Path(repo_path).resolve()
        self.timeout = timeout
        self.java_home = java_home or os.environ.get("JAVA_HOME", "")
        self.junit_lib_path = junit_lib_path or self._find_junit_libs()
        self.dependency_classpath = dependency_classpath
        self.target_package = target_package
        # Expected public class the generated code MUST define (e.g. "Elements").
        # The generated impl is written to <target_package>/<target_class>.java so
        # its compiled class SHADOWS the ground-truth one on the closure
        # classpath. If the generated code is empty or fails to declare this
        # class, the reconstruction FAILED and is scored phi=0 — it must never
        # fall through to silently testing the ground-truth target.
        self.target_class = target_class or ""
        # Real entity qualnames of the module under test (e.g.
        # ["Collector", "Collector.collect", ...]). When provided, test->entity
        # attribution resolves against THESE real methods instead of a
        # hardcoded list, so it generalizes to any repo (not just the toy data).
        self.entities = list(entities) if entities else []
        # class_name -> {simple method names} derived from self.entities.
        self._methods_by_class: dict = {}
        for qn in self.entities:
            if "." in qn:
                cls, _, meth = qn.partition(".")
                self._methods_by_class.setdefault(cls, set()).add(meth)

        # Java commands
        self.javac = self._find_javac()
        self.java = self._find_java()

        # JaCoCo (line/branch coverage of the target class), if present in libs/.
        _libs = Path(__file__).parent.parent / "libs"
        self._jacoco_agent = _libs / "jacocoagent.jar"
        self._jacoco_cli = _libs / "jacococli.jar"

    def _jacoco_available(self) -> bool:
        return self._jacoco_agent.exists() and self._jacoco_cli.exists()

    def balance_tests(self, max_per_entity: int = 2, verbose: bool = False):
        """Balance test distribution by limiting tests per function entity.

        Parses the test file, groups tests by entity (via _test_name_to_entity),
        and if any entity has more than max_per_entity tests, samples down.
        Rewrites the test file in place.

        Args:
            max_per_entity: Maximum tests per function entity.
            verbose: Print balancing info.
        """
        import random
        content = self.test_suite_path.read_text()

        # Extract individual test methods with their full text
        # Pattern: from @Test to the closing brace of the method
        test_pattern = re.compile(
            r'([ \t]*@Test\b.*?void\s+(test_?\w+)\s*\(\s*\)\s*\{)',
            re.DOTALL
        )

        # Find all test methods and their positions
        tests = []  # list of (entity, method_name, start_pos, end_pos)
        for match in test_pattern.finditer(content):
            method_name = match.group(2)
            # Find the start of annotations (might have @DisplayName before @Test)
            # Walk backwards from @Test to find preceding annotations
            test_start = match.start()
            prefix = content[:test_start].rstrip()
            while prefix.endswith(')'):
                # Find the @DisplayName or other annotation before
                ann_match = re.search(r'@\w+\s*\([^)]*\)\s*$', prefix)
                if ann_match:
                    test_start = test_start - (len(prefix) - ann_match.start())
                    prefix = content[:test_start].rstrip()
                else:
                    break
            # Also catch bare annotations like @Test without params
            while True:
                ann_match = re.search(r'@\w+\s*$', prefix)
                if ann_match and '@Test' not in content[test_start:match.end()].split('\n')[0]:
                    test_start = test_start - (len(prefix) - ann_match.start())
                    prefix = content[:test_start].rstrip()
                else:
                    break

            # Find the end of the method (matching braces)
            brace_start = match.end() - 1  # position of opening {
            depth = 1
            pos = brace_start + 1
            while pos < len(content) and depth > 0:
                if content[pos] == '{':
                    depth += 1
                elif content[pos] == '}':
                    depth -= 1
                pos += 1
            test_end = pos

            entity = self._test_name_to_entity(method_name)
            tests.append({
                'entity': entity or 'unknown',
                'method_name': method_name,
                'start': test_start,
                'end': test_end,
                'text': content[test_start:test_end],
            })

        if not tests:
            return

        # Group by entity
        from collections import defaultdict
        entity_groups = defaultdict(list)
        for t in tests:
            entity_groups[t['entity']].append(t)

        # Determine which tests to keep
        keep_tests = set()
        random.seed(42)  # deterministic sampling
        for entity, group in entity_groups.items():
            if len(group) <= max_per_entity:
                for t in group:
                    keep_tests.add(t['method_name'])
            else:
                sampled = random.sample(group, max_per_entity)
                for t in sampled:
                    keep_tests.add(t['method_name'])

        # Remove tests not in keep set (process in reverse order to preserve positions)
        removed = []
        tests_sorted = sorted(tests, key=lambda t: t['start'], reverse=True)
        for t in tests_sorted:
            if t['method_name'] not in keep_tests:
                # Remove the test text and any trailing whitespace/newlines
                end = t['end']
                while end < len(content) and content[end] in '\n\r \t':
                    end += 1
                start = t['start']
                # Also remove leading whitespace on the same line
                while start > 0 and content[start - 1] in ' \t':
                    start -= 1
                content = content[:start] + content[end:]
                removed.append((t['entity'], t['method_name']))

        # Write back
        self.test_suite_path.write_text(content)

        if verbose:
            total_before = len(tests)
            total_after = len(keep_tests)
            print(f"Test balancing: {total_before} → {total_after} tests "
                  f"(max {max_per_entity} per entity)")
            for entity, group in sorted(entity_groups.items()):
                kept = sum(1 for t in group if t['method_name'] in keep_tests)
                print(f"  {entity}: {len(group)} → {kept}")

    def _find_javac(self) -> str:
        """Find javac compiler."""
        # Try explicit java_home first
        if self.java_home:
            javac = os.path.join(self.java_home, "bin", "javac")
            if os.path.exists(javac):
                return javac

        # Try default JDK path
        default_javac = os.path.join(self.DEFAULT_JDK_PATH, "bin", "javac")
        if os.path.exists(default_javac):
            return default_javac

        # Try system path
        return "javac"

    def _find_java(self) -> str:
        """Find java runtime."""
        # Try explicit java_home first
        if self.java_home:
            java = os.path.join(self.java_home, "bin", "java")
            if os.path.exists(java):
                return java

        # Try default JDK path
        default_java = os.path.join(self.DEFAULT_JDK_PATH, "bin", "java")
        if os.path.exists(default_java):
            return default_java

        # Try system path
        return "java"

    def _find_junit_libs(self) -> str:
        """Find JUnit library path."""
        # Check multiple locations for JUnit JARs
        possible_paths = [
            # Project root libs (docsearch-japan/libs)
            Path(__file__).parent.parent / "libs",
            # Local libs in doc_generator
            Path(__file__).parent / "libs",
            # Dataset-specific libs
            self.repo_path / "libs",
            # System locations
            Path.home() / ".m2" / "repository",
            Path("/usr/share/java"),
            Path("/usr/local/lib/java"),
        ]

        for path in possible_paths:
            if path.exists() and path.is_dir():
                jars = [f for f in path.iterdir() if f.suffix == '.jar']
                if jars:
                    return str(path)

        return ""

    def _get_classpath(self, build_dir: str) -> str:
        """Build classpath string for Java compilation/execution.

        Order: generated ``build_dir`` FIRST (so freshly compiled generated
        classes shadow the ground-truth ones), then the closure
        ``dependency_classpath`` (if set), then the JUnit jars. The
        generated-first ordering is what lets a single recompiled target file
        override its ground-truth ``.class`` while all deps resolve against the
        closure.
        """
        classpath_parts = [build_dir]

        # Closure deps (ground-truth classes dir + external jars) after the
        # generated build dir so generated classes win on resolution.
        if self.dependency_classpath:
            classpath_parts.append(self.dependency_classpath)

        # Find JUnit JARs
        junit_lib = self._find_junit_libs()
        if junit_lib and os.path.exists(junit_lib):
            for jar_file in os.listdir(junit_lib):
                if jar_file.endswith('.jar'):
                    classpath_parts.append(os.path.join(junit_lib, jar_file))

        # If no JUnit/dep jars were added, try Maven repository
        if len(classpath_parts) == (2 if self.dependency_classpath else 1):
            maven_base = os.path.expanduser("~/.m2/repository")
            junit_paths = [
                f"{maven_base}/org/junit/jupiter/junit-jupiter-api/5.9.0/junit-jupiter-api-5.9.0.jar",
                f"{maven_base}/org/junit/jupiter/junit-jupiter-engine/5.9.0/junit-jupiter-engine-5.9.0.jar",
                f"{maven_base}/org/junit/platform/junit-platform-launcher/1.9.0/junit-platform-launcher-1.9.0.jar",
                f"{maven_base}/org/junit/platform/junit-platform-engine/1.9.0/junit-platform-engine-1.9.0.jar",
                f"{maven_base}/org/junit/platform/junit-platform-commons/1.9.0/junit-platform-commons-1.9.0.jar",
                f"{maven_base}/org/opentest4j/opentest4j/1.2.0/opentest4j-1.2.0.jar",
                f"{maven_base}/org/apiguardian/apiguardian-api/1.1.2/apiguardian-api-1.1.2.jar",
            ]

            for jar_path in junit_paths:
                if os.path.exists(jar_path):
                    classpath_parts.append(jar_path)

        return ":".join(classpath_parts)

    @staticmethod
    def _declared_package(source: str) -> str:
        """The package declared by ``package ...;`` in ``source`` ("" if none)."""
        m = re.search(r'^\s*package\s+([\w.]+)\s*;', source, re.MULTILINE)
        return m.group(1) if m else ""

    def _package_dir(self, build_dir: str, source: str) -> str:
        """Directory under ``build_dir`` a source file must be written to.

        Honors any ``package ...;`` declaration in the source (which is NOT
        stripped), falling back to ``self.target_package``. javac requires a
        packaged source to live under a matching directory tree. Returns
        ``build_dir`` itself for the default (unnamed) package, preserving the
        existing single-file flow.
        """
        package = self._declared_package(source) or self.target_package
        if not package:
            return build_dir
        pkg_dir = os.path.join(build_dir, *package.split("."))
        os.makedirs(pkg_dir, exist_ok=True)
        return pkg_dir

    def run(self, generated_code: str, iteration: int = 0,
            measure_coverage: bool = False) -> TestResult:
        """
        Run tests with the generated Java code.

        Args:
            generated_code: The generated Java code
            iteration: Current iteration number (for logging)
            measure_coverage: When True (and JaCoCo is available), also measure
                line/branch coverage of the TARGET class and fill the
                ``line_rate``/``branch_rate``/``covered_lines``/``total_lines``
                fields of the result.

        Returns:
            TestResult with pass/fail counts and errors
        """
        result = TestResult()

        # Create temporary working directory
        build_dir = tempfile.mkdtemp(prefix="java_test_")

        try:
            # Determine the top-level type name to name the .java file after.
            # The target may be ANY top-level type kind (class / interface / enum /
            # record / annotation) and ANY visibility (public OR package-private,
            # e.g. jsoup's `abstract class NodeEvaluator` and `public interface
            # NodeVisitor`), so do not assume `public class`.
            _TYPE_KW = r'(?:class|interface|enum|record|@interface)'
            if self.target_class:
                # phi INTEGRITY GUARD (multi-file repo / closure mode): the
                # generated code MUST be non-empty and DECLARE THE EXPECTED TYPE
                # so its compiled class shadows the ground-truth one on the
                # closure classpath. Otherwise the tests would silently run
                # against GROUND TRUTH and pass (false phi=1.0). A failed/empty/
                # mis-named reconstruction is phi=0, not a pass. The expected type
                # may be a class/interface/enum/record of any visibility.
                if not (generated_code or "").strip():
                    result.compile_error = (
                        "empty generated code: reconstruction failed "
                        f"(expected type '{self.target_class}')"
                    )
                    return result
                if not re.search(_TYPE_KW + r'\s+' + re.escape(self.target_class) + r'\b',
                                 generated_code):
                    result.compile_error = (
                        f"generated code does not declare expected type "
                        f"'{self.target_class}'; refusing to test against the "
                        "ground-truth target"
                    )
                    return result
                impl_class = self.target_class
            else:
                # Single-file mode: name the file after the declared top-level
                # type (public preferred), falling back to a default.
                m = re.search(r'public\s+(?:final\s+|abstract\s+)*' + _TYPE_KW + r'\s+(\w+)',
                              generated_code) or re.search(_TYPE_KW + r'\s+(\w+)', generated_code)
                impl_class = m.group(1) if m else "Indicators"

            impl_filename = impl_class + ".java"
            impl_file = os.path.join(self._package_dir(build_dir, generated_code), impl_filename)
            with open(impl_file, 'w', encoding='utf-8') as f:
                f.write(generated_code)

            # Copy test file to build directory with correct filename
            # javac requires filename to match public class name
            test_content = self.test_suite_path.read_text()
            class_match = re.search(r'public\s+class\s+(\w+)', test_content)
            if class_match:
                test_filename = class_match.group(1) + ".java"
            else:
                test_filename = self.test_suite_path.name
            test_dest = os.path.join(self._package_dir(build_dir, test_content), test_filename)
            with open(test_dest, 'w', encoding='utf-8') as f:
                f.write(test_content)

            # Step 1: Compile the code
            compile_result = self._compile(build_dir, [impl_file, test_dest])
            if compile_result.compile_error:
                return compile_result

            # Step 2: Run tests (optionally under the JaCoCo agent).
            do_cov = measure_coverage and self._jacoco_available()
            jacoco_exec = os.path.join(build_dir, "jacoco.exec") if do_cov else None
            test_result = self._run_tests(build_dir, jacoco_exec=jacoco_exec)

            # Step 3: measure coverage of the TARGET class, before cleanup.
            if do_cov and os.path.exists(jacoco_exec):
                try:
                    self._fill_coverage(test_result, build_dir, jacoco_exec, impl_class)
                except Exception as exc:
                    logger.debug("JaCoCo coverage measurement failed: %s", exc)
            return test_result

        except Exception as e:
            result.runtime_error = str(e)
            result.errors.append(f"Execution error: {e}")
            return result

        finally:
            if os.path.exists(build_dir):
                shutil.rmtree(build_dir, ignore_errors=True)

    def _compile(self, build_dir: str, java_files: list[str]) -> TestResult:
        """Compile Java files.

        Args:
            build_dir: Directory for compiled classes.
            java_files: List of .java files to compile.

        Returns:
            TestResult with compilation result.
        """
        result = TestResult()
        classpath = self._get_classpath(build_dir)

        cmd = [
            self.javac,
            "-d", build_dir,
            "-cp", classpath,
            "-source", "17",
            "-target", "17",
        ] + java_files

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            result.output = proc.stdout + proc.stderr

            if proc.returncode != 0:
                result.compile_error = proc.stderr
                # Parse compilation errors
                errors = self._parse_javac_errors(proc.stderr)
                result.errors.extend(errors)
                result.failed = 1
                result.total = 1
                return result

        except subprocess.TimeoutExpired:
            result.compile_error = "Compilation timeout"
            result.errors.append("Compilation timeout after 60 seconds")
            result.failed = 1
            result.total = 1
        except Exception as e:
            result.compile_error = str(e)
            result.errors.append(f"Compilation error: {e}")
            result.failed = 1
            result.total = 1

        return result

    def _parse_javac_errors(self, stderr: str) -> list[str]:
        """Parse javac compilation errors.

        Args:
            stderr: javac stderr output.

        Returns:
            List of error messages.
        """
        errors = []
        # Pattern: FileName.java:line: error: message
        pattern = r'(\w+\.java):(\d+):\s*error:\s*(.+?)(?=\n\w+\.java:\d+:|$)'
        matches = re.findall(pattern, stderr, re.DOTALL)

        for match in matches[:10]:  # Limit to 10 errors
            filename, line, message = match
            errors.append(f"{filename}:{line}: {message.strip()}")

        # If no structured errors found, add raw message
        if not errors and stderr.strip():
            errors.append(f"Compilation failed: {stderr[:500]}")

        return errors

    def _run_tests(self, build_dir: str, jacoco_exec=None) -> TestResult:
        """Run JUnit tests.

        Args:
            build_dir: Directory containing compiled classes.

        Returns:
            TestResult with test results.
        """
        result = TestResult()
        classpath = self._get_classpath(build_dir)

        # Use JUnit Console Launcher, optionally under the JaCoCo agent so we can
        # measure line/branch coverage of the target class.
        cmd = [self.java]
        if jacoco_exec is not None and self._jacoco_agent.exists():
            cmd.append(f"-javaagent:{self._jacoco_agent}=destfile={jacoco_exec}")
        cmd += [
            "-cp", classpath,
            "org.junit.platform.console.ConsoleLauncher",
            "--scan-classpath",
            "--details", "verbose",
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=build_dir
            )

            result.output = proc.stdout + proc.stderr

            # Parse test results
            self._parse_test_output(proc.stdout + proc.stderr, result)

        except subprocess.TimeoutExpired:
            result.runtime_error = "Test execution timeout"
            result.errors.append(f"Test execution timeout after {self.timeout} seconds")
            result.failed = 1
            result.total = 1
        except Exception as e:
            result.runtime_error = str(e)
            result.errors.append(f"Test execution error: {e}")
            result.failed = 1
            result.total = 1

        return result

    def _fill_coverage(self, result: "TestResult", build_dir: str,
                       exec_file: str, target_class: str) -> None:
        """Generate a JaCoCo CSV report and fill ``result``'s coverage fields
        with line/branch coverage of the TARGET class (and its nested classes),
        excluding the test class.
        """
        csv_path = os.path.join(build_dir, "jacoco.csv")
        cmd = [
            self.java, "-jar", str(self._jacoco_cli), "report", exec_file,
            "--classfiles", build_dir, "--csv", csv_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0 or not os.path.exists(csv_path):
            logger.debug("jacoco report failed: %s", proc.stderr[:300])
            return

        lc = lm = bc = bm = 0
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                cls = row.get("CLASS", "")
                # Target class + its nested classes; never the test class.
                if cls == target_class or cls.startswith(target_class + "$") \
                        or cls.startswith(target_class + "."):
                    lm += int(row.get("LINE_MISSED", 0))
                    lc += int(row.get("LINE_COVERED", 0))
                    bm += int(row.get("BRANCH_MISSED", 0))
                    bc += int(row.get("BRANCH_COVERED", 0))
        total = lc + lm
        result.covered_lines = lc
        result.total_lines = total
        result.line_rate = (lc / total) if total else 0.0
        result.branch_rate = (bc / (bc + bm)) if (bc + bm) else 0.0

    def _parse_test_output(self, output: str, result: TestResult):
        """Parse JUnit test output to extract results.

        Args:
            output: Raw test output.
            result: TestResult to populate.
        """
        # Parse JUnit Platform Console output format
        # Example: "[ 24 tests found ]"
        # Example: "[ 20 tests successful ]"
        # Example: "[ 4 tests failed ]"

        found_match = re.search(r'\[\s*(\d+)\s+tests?\s+found\s*\]', output)
        success_match = re.search(r'\[\s*(\d+)\s+tests?\s+successful\s*\]', output)
        failed_match = re.search(r'\[\s*(\d+)\s+tests?\s+failed\s*\]', output)

        if found_match:
            result.total = int(found_match.group(1))

        if success_match:
            result.passed = int(success_match.group(1))

        if failed_match:
            result.failed = int(failed_match.group(1))

        # If couldn't parse standard format, try alternative
        if result.total == 0:
            self._parse_legacy_output(output, result)

        # Extract failure messages with entity associations
        self._extract_failure_messages(output, result)

    def _parse_legacy_output(self, output: str, result: TestResult):
        """Parse legacy JUnit output format."""
        # Try to find "Tests run: X, Failures: Y, Errors: Z"
        legacy_match = re.search(
            r'Tests\s+run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)',
            output
        )

        if legacy_match:
            result.total = int(legacy_match.group(1))
            result.failed = int(legacy_match.group(2)) + int(legacy_match.group(3))
            result.passed = result.total - result.failed

    def _extract_failure_messages(self, output: str, result: TestResult):
        """Extract failure messages from test output.

        Args:
            output: Raw test output.
            result: TestResult to add errors to.
        """
        # Remove ANSI color codes for easier parsing
        ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
        clean_output = ansi_escape.sub('', output)

        # Pattern to match failed test method names in JUnit verbose output
        # Example: "methodName = 'test_Renko_getOhlcData_single_row'"
        # followed by "status: ✘ FAILED"
        method_pattern = r"methodName\s*=\s*'(test_\w+)'"
        status_pattern = r"status:\s*[✘✗]\s*FAILED"

        # Find all test methods and their status
        lines = clean_output.split('\n')
        current_test = None
        failed_tests = []

        for i, line in enumerate(lines):
            method_match = re.search(method_pattern, line)
            if method_match:
                current_test = method_match.group(1)

            if current_test and re.search(status_pattern, line):
                failed_tests.append(current_test)
                current_test = None

        # Pattern to match assertion failures with context
        assertion_pattern = r'expected:\s*<(.+?)>\s+but\s+was:\s*<(.+?)>'
        assertions = re.findall(assertion_pattern, clean_output)

        # Add errors with entity context
        for test_name in failed_tests[:10]:
            entity = self._test_name_to_entity(test_name)
            if entity:
                result.errors.append(f"Target: {entity} | FAILED: {test_name}")
            else:
                result.errors.append(f"FAILED: {test_name}")

        # Add assertion details
        for expected, actual in assertions[:5]:
            result.errors.append(f"AssertionError: expected <{expected}> but was <{actual}>")

    @staticmethod
    def _split_camel_and_snake(text: str) -> list[str]:
        """Split a string by both underscores and camelCase boundaries.

        Examples:
            'getOhlcData' -> ['get', 'ohlc', 'data']
            'get_ohlc_data' -> ['get', 'ohlc', 'data']
            'getState_uptrend' -> ['get', 'state', 'uptrend']
        """
        # First split by underscore, then split each part by camelCase
        result = []
        for part in text.split('_'):
            if part:
                tokens = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', part)
                result.extend(t.lower() for t in tokens)
        return result

    def _test_name_to_entity(self, test_name: str) -> Optional[str]:
        """Convert test name to entity name.

        Handles both snake_case and camelCase method names:
            test_Renko_get_ohlc_data_reversal -> Renko.getOhlcData
            test_PnF_getState_uptrend         -> PnF.getState
            testRenkoGetOhlcData              -> Renko.getOhlcData

        Args:
            test_name: Test method name.

        Returns:
            Entity name (e.g., Renko.getOhlcData) or None.
        """
        # Handle both test_ prefix and test prefix (camelCase)
        if test_name.startswith("test_"):
            remainder = test_name[5:]
        elif test_name.startswith("test"):
            remainder = test_name[4:]
        else:
            return None

        if not remainder:
            return None

        # ENTITY-VALIDATED fast path: when we know the real module entities,
        # resolve strictly against them so a free-form test name can never
        # invent a non-existent entity (e.g. "test_Collector_placeholder_collect"
        # must map to the REAL Collector.collect, not a fabricated
        # Collector.placeholderCollect). We tokenize the test name and look for
        # the longest real method of a real class appearing as a contiguous token
        # run anywhere in the name.
        if self._methods_by_class:
            name_tokens = self._split_camel_and_snake(remainder)
            lowered = [t.lower() for t in name_tokens]

            def _contains(method: str) -> bool:
                mt = [t.lower() for t in self._split_camel_and_snake(method)]
                if not mt:
                    return False
                for i in range(len(lowered) - len(mt) + 1):
                    if lowered[i:i + len(mt)] == mt:
                        return True
                return False

            # Pick the class whose name appears in the test name (longest first).
            for cls in sorted(self._methods_by_class, key=len, reverse=True):
                if cls.lower() not in test_name.lower():
                    continue
                methods = sorted(self._methods_by_class[cls], key=len, reverse=True)
                for meth in methods:
                    if _contains(meth):
                        return f"{cls}.{meth}"
                # Class named but no method matched: attribute to the class only
                # if the class itself is a real (documented) entity.
                if cls in self.entities:
                    return cls
            return None  # no real class/method recognizable — do not fabricate

        # Split by underscore first to find class name
        underscore_parts = remainder.split('_')

        # Find class name (first PascalCase part)
        class_name = None
        method_start_idx = None

        for i, part in enumerate(underscore_parts):
            if part and part[0].isupper():
                # Check if this is a known class name or looks like one
                # Also handle camelCase like "RenkoGetOhlcData" - extract class prefix
                class_name = part
                method_start_idx = i + 1
                break

        if not class_name:
            return None

        # For pure camelCase (testRenkoGetOhlcData), class_name might contain
        # the method name too (e.g., "RenkoGetOhlcData"). Split it further.
        if method_start_idx is not None and method_start_idx >= len(underscore_parts):
            # No underscore parts after class — might be camelCase-only
            tokens = re.findall(r'[A-Z][a-z]*|[A-Z]+(?=[A-Z]|$)', class_name)
            if len(tokens) > 1:
                class_name = tokens[0]
                after_class = ''.join(tokens[1:])
                # Re-split: treat after_class as the method portion
                method_tokens = self._split_camel_and_snake(after_class)
            else:
                return class_name
        else:
            # Collect everything after class_name, flatten camelCase within each part
            raw_method_parts = underscore_parts[method_start_idx:]
            method_tokens = self._split_camel_and_snake('_'.join(raw_method_parts))

        if not method_tokens:
            return class_name

        # Method names to match against. Prefer the REAL methods of the detected
        # class (from self.entities) so attribution generalizes to ANY repo;
        # fall back to the toy-dataset list only when no entity universe was
        # supplied. Longest-first so "getOhlcData" matches before "get".
        if self._methods_by_class:
            known_methods = sorted(
                self._methods_by_class.get(class_name, set()),
                key=len, reverse=True,
            )
        else:
            known_methods = [
                "getOhlcData", "getState", "roundIt", "periodCloseBricks",
                "priceMovementBricks", "uptrendReversal", "downtrendReversal",
                "copy", "tail", "minOf", "maxOf", "get", "add", "size"
            ]

        # Try to find a known method name
        for method in known_methods:
            snake_parts = self._split_camel_and_snake(method)

            if len(method_tokens) >= len(snake_parts):
                if method_tokens[:len(snake_parts)] == snake_parts:
                    return f"{class_name}.{method}"

        # Fallback: build method name from tokens
        test_suffixes = {"basic", "reversal", "single", "row", "uptrend", "downtrend",
                         "returns", "true", "false", "insufficient", "data", "continual",
                         "boundary", "minimal", "large", "empty", "no", "with"}

        method_name_tokens = []
        for token in method_tokens:
            if token in test_suffixes and method_name_tokens:
                break
            method_name_tokens.append(token)

        if method_name_tokens:
            # Convert to camelCase
            method_name = method_name_tokens[0]
            for t in method_name_tokens[1:]:
                method_name += t.capitalize()
            return f"{class_name}.{method_name}"

        return class_name

        return None

    def check_environment(self) -> dict:
        """Check if Java environment is properly configured.

        Returns:
            Dict with environment status.
        """
        status = {
            "java_found": False,
            "javac_found": False,
            "junit_found": False,
            "java_version": None,
            "errors": []
        }

        # Check java
        try:
            proc = subprocess.run(
                [self.java, "-version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if proc.returncode == 0:
                status["java_found"] = True
                version_match = re.search(r'version "([^"]+)"', proc.stderr)
                if version_match:
                    status["java_version"] = version_match.group(1)
        except Exception as e:
            status["errors"].append(f"Java not found: {e}")

        # Check javac
        try:
            proc = subprocess.run(
                [self.javac, "-version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            status["javac_found"] = proc.returncode == 0
        except Exception as e:
            status["errors"].append(f"javac not found: {e}")

        # Check JUnit
        classpath = self._get_classpath(".")
        if "junit" in classpath.lower():
            status["junit_found"] = True
        else:
            status["errors"].append("JUnit JARs not found in classpath")

        return status
