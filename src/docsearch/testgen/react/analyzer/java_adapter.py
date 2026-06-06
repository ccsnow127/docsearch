"""Java language adapter using javalang, JUnit5, and JaCoCo."""

import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
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


# Maven pom.xml template with JUnit5 and JaCoCo
POM_TEMPLATE = '''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.test</groupId>
    <artifactId>test-project</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.10.0</junit.version>
        <jacoco.version>0.8.11</jacoco.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.11.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.2</version>
            </plugin>
            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>${jacoco.version}</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>prepare-agent</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>report</id>
                        <phase>test</phase>
                        <goals>
                            <goal>report</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
'''


# External dependencies that should be mocked
EXTERNAL_PACKAGES = {
    # Database
    "java.sql", "javax.sql", "org.hibernate", "javax.persistence",
    # Network
    "java.net", "org.apache.http", "okhttp3", "retrofit2",
    # Filesystem
    "java.io", "java.nio.file",
    # Time
    "java.time.Clock", "java.time.Instant",
    # Random
    "java.util.Random", "java.security.SecureRandom",
}


class JavaAdapter(LanguageAdapter):
    """Java language adapter using javalang, JUnit5, and JaCoCo."""

    def __init__(
        self,
        dependency_classpath: str = "",
        target_package: str = "",
        repo_root: Optional[str] = None,
    ):
        """Initialize the Java adapter.

        Args:
            dependency_classpath: The repo closure ``deps_classpath``
                (ground-truth classes dir + external jars) to compile/run the
                generated test file against. Empty keeps the self-contained
                single-file Maven flow used when there is no repo closure.
            target_package: Java package of the target file (e.g.
                ``"org.jsoup.select"``). When set, the closure path writes the
                ground-truth target and the generated test under their package
                directory so javac/JUnit see package-structured classes. Empty
                means the default (unnamed) package.
            repo_root: Repository root of the closure (passed through to the
                :class:`~docsearch.java_test_executor.JavaTestExecutor` so it
                resolves JUnit jars relative to the real repo as well).
        """
        self._javalang = None
        self.dependency_classpath = dependency_classpath
        self.target_package = target_package
        self.repo_root = repo_root

    @property
    def javalang(self):
        """Lazy import javalang."""
        if self._javalang is None:
            try:
                import javalang
                self._javalang = javalang
            except ImportError:
                raise ImportError(
                    "javalang is required for Java support. "
                    "Install it with: pip install javalang"
                )
        return self._javalang

    @property
    def language(self) -> Language:
        return Language.JAVA

    def extract_functions(self, source_code: str) -> list[FunctionInfo]:
        """Extract public and protected methods from Java source code."""
        functions = []
        try:
            tree = self.javalang.parse.parse(source_code)
        except Exception:
            return functions

        source_lines = source_code.splitlines()

        for path, node in tree.filter(self.javalang.tree.MethodDeclaration):
            # Skip private methods
            if "private" in (node.modifiers or []):
                continue

            # Get class name from path
            class_name = None
            for item in path:
                if isinstance(item, self.javalang.tree.ClassDeclaration):
                    class_name = item.name

            func_info = self._extract_method_info(node, source_code, source_lines, class_name)
            functions.append(func_info)

        return functions

    def _extract_method_info(
        self,
        node,
        source_code: str,
        source_lines: list[str],
        class_name: Optional[str],
    ) -> FunctionInfo:
        """Extract FunctionInfo from a javalang method node."""
        # Get signature
        signature = self._get_signature(node)

        # Get parameter types
        param_types = {}
        if node.parameters:
            for param in node.parameters:
                param_types[param.name] = self._type_to_string(param.type)

        # Get return type
        return_type = None
        if node.return_type:
            return_type = self._type_to_string(node.return_type)

        # Get body (approximate from position)
        start_line = node.position.line if node.position else 0
        body = self._extract_method_body(source_lines, start_line)

        # Get docstring (Javadoc)
        docstring = None
        if node.documentation:
            docstring = node.documentation

        is_public = "public" in (node.modifiers or []) or "protected" in (node.modifiers or [])

        return FunctionInfo(
            name=node.name,
            signature=signature,
            body=body,
            docstring=docstring,
            is_public=is_public,
            class_name=class_name,
            param_types=param_types,
            return_type=return_type,
            start_line=start_line,
            end_line=start_line + body.count("\n"),
        )

    def _get_signature(self, node) -> str:
        """Get method signature as a string."""
        modifiers = " ".join(node.modifiers) if node.modifiers else ""
        return_type = self._type_to_string(node.return_type) if node.return_type else "void"

        params = []
        if node.parameters:
            for param in node.parameters:
                param_type = self._type_to_string(param.type)
                params.append(f"{param_type} {param.name}")

        return f"{modifiers} {return_type} {node.name}({', '.join(params)})".strip()

    def _type_to_string(self, type_node) -> str:
        """Convert a javalang type node to a string."""
        if type_node is None:
            return "void"

        if hasattr(type_node, "name"):
            base = type_node.name
            if hasattr(type_node, "arguments") and type_node.arguments:
                args = ", ".join(self._type_to_string(arg.type) for arg in type_node.arguments)
                base += f"<{args}>"
            if hasattr(type_node, "dimensions") and type_node.dimensions:
                base += "[]" * len(type_node.dimensions)
            return base

        return str(type_node)

    def _extract_method_body(self, source_lines: list[str], start_line: int) -> str:
        """Extract method body from source lines."""
        if start_line <= 0 or start_line > len(source_lines):
            return ""

        # Find opening brace
        brace_count = 0
        in_method = False
        body_lines = []

        for i in range(start_line - 1, len(source_lines)):
            line = source_lines[i]
            body_lines.append(line)

            for char in line:
                if char == "{":
                    brace_count += 1
                    in_method = True
                elif char == "}":
                    brace_count -= 1

            if in_method and brace_count == 0:
                break

        return "\n".join(body_lines)

    def get_imports(self, source_code: str) -> list[str]:
        """Get import statements from Java source code."""
        imports = []
        try:
            tree = self.javalang.parse.parse(source_code)
            for imp in tree.imports:
                path = imp.path
                if imp.static:
                    imports.append(f"import static {path};")
                else:
                    imports.append(f"import {path};")
        except Exception:
            # Fall back to regex
            for match in re.finditer(r"^import\s+(static\s+)?[\w.]+;", source_code, re.MULTILINE):
                imports.append(match.group())

        return imports

    def get_constructors(self, source_code: str) -> list[str]:
        """Get constructor signatures for classes in the source code."""
        constructors = []
        try:
            tree = self.javalang.parse.parse(source_code)

            for _, node in tree.filter(self.javalang.tree.ConstructorDeclaration):
                # Get class name
                class_name = None
                for _, class_node in tree.filter(self.javalang.tree.ClassDeclaration):
                    class_name = class_node.name
                    break

                params = []
                if node.parameters:
                    for param in node.parameters:
                        param_type = self._type_to_string(param.type)
                        params.append(f"{param_type} {param.name}")

                if class_name:
                    constructors.append(f"new {class_name}({', '.join(params)})")

        except Exception:
            pass

        return constructors

    def identify_external_dependencies(
        self, source_code: str
    ) -> list[DependencyInfo]:
        """Identify external dependencies that should be mocked."""
        dependencies = []

        try:
            tree = self.javalang.parse.parse(source_code)

            for imp in tree.imports:
                path = imp.path
                for ext_pkg in EXTERNAL_PACKAGES:
                    if path.startswith(ext_pkg):
                        dep_type = self._categorize_dependency(path)
                        dependencies.append(
                            DependencyInfo(
                                name=path.split(".")[-1],
                                type=dep_type,
                                is_external=True,
                                needs_mock=True,
                                module_path=path,
                            )
                        )
                        break

        except Exception:
            pass

        return dependencies

    def _categorize_dependency(self, import_path: str) -> str:
        """Categorize a dependency by type."""
        if "sql" in import_path or "hibernate" in import_path or "persistence" in import_path:
            return "database"
        elif "net" in import_path or "http" in import_path:
            return "network"
        elif "io" in import_path or "nio" in import_path:
            return "filesystem"
        elif "time" in import_path:
            return "time"
        elif "Random" in import_path:
            return "random"
        return "other"

    def check_syntax(self, code: str) -> tuple[bool, Optional[str]]:
        """Check if Java code has valid syntax."""
        try:
            self.javalang.parse.parse(code)
            return True, None
        except Exception as e:
            return False, str(e)

    def _setup_maven_project(
        self,
        source_file: Path,
        test_file: Path,
    ) -> Path:
        """Set up a temporary Maven project structure.

        Creates:
            temp_dir/
            ├── pom.xml
            └── src/
                ├── main/java/
                │   └── <SourceFile>.java
                └── test/java/
                    └── <TestFile>.java

        Returns:
            Path to the temporary Maven project directory.
        """
        # Create temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix="java_test_"))

        # Create directory structure
        main_java = temp_dir / "src" / "main" / "java"
        test_java = temp_dir / "src" / "test" / "java"
        main_java.mkdir(parents=True)
        test_java.mkdir(parents=True)

        # Write pom.xml
        (temp_dir / "pom.xml").write_text(POM_TEMPLATE)

        # Copy source file
        shutil.copy(source_file, main_java / source_file.name)

        # Copy test file
        shutil.copy(test_file, test_java / test_file.name)

        return temp_dir

    def _run_against_closure(
        self,
        test_file: Path,
        source_file: Path,
        timeout: int,
    ) -> TestResult:
        """Compile + run the test file against the repo closure (no temp Maven).

        Reuses :class:`docsearch.java_test_executor.JavaTestExecutor`, which
        compiles the GROUND-TRUTH target source together with the generated test
        file against ``dependency_classpath`` (the closure) with the freshly
        compiled classes FIRST on the classpath, preserving ``package ...;``
        declarations and placing files under their package directories. This is
        the path taken whenever a closure is configured, so the generated tests
        see the real repo rather than an isolated default-package project.
        """
        from docsearch.java_test_executor import JavaTestExecutor

        ground_truth_source = source_file.read_text(encoding="utf-8", errors="replace")
        executor = JavaTestExecutor(
            test_suite_path=str(test_file),
            target_module=source_file.stem,
            repo_path=self.repo_root or str(source_file.parent),
            timeout=timeout,
            dependency_classpath=self.dependency_classpath,
            target_package=self.target_package,
        )
        exec_result = executor.run(ground_truth_source)
        return self._convert_executor_result(exec_result)

    @staticmethod
    def _convert_executor_result(exec_result) -> TestResult:
        """Map a :class:`JavaTestExecutor` result onto our :class:`TestResult`.

        A compile error is surfaced as one erroring test carrying the javac
        output (so the react loop's failing block shows the real diagnostic);
        otherwise pass/fail counts are copied across.
        """
        if exec_result.compile_error:
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                output=exec_result.output or exec_result.compile_error,
                failure_details=[{
                    "type": "CompilationError",
                    "message": "\n".join(exec_result.errors[:10])
                    or exec_result.compile_error,
                }],
            )
        failure_details = [
            {"type": "TestFailure", "message": msg}
            for msg in (exec_result.errors or [])[:10]
        ]
        # JavaTestExecutor counts compile/runtime trouble as failed; map the
        # remainder to failed (JUnit does not separate failures vs errors here).
        return TestResult(
            passed=exec_result.passed,
            failed=exec_result.failed,
            errors=0,
            output=exec_result.output,
            failure_details=failure_details,
        )

    def run_tests(
        self,
        test_file: Path,
        source_file: Path,
        timeout: int = 60,
    ) -> TestResult:
        """Run JUnit5 tests on the test file.

        With a repo closure configured (``dependency_classpath``), the test file
        is compiled and run against the GROUND-TRUTH target plus the closure on
        the classpath. Otherwise the self-contained temp-Maven project is used.
        """
        if self.dependency_classpath:
            return self._run_against_closure(test_file, source_file, timeout)

        # Set up temporary Maven project
        project_dir = self._setup_maven_project(source_file, test_file)

        try:
            # Run maven test
            result = subprocess.run(
                ["mvn", "test"],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=project_dir,
            )

            return self._parse_maven_output(
                result.stdout + result.stderr,
                result.returncode
            )

        except FileNotFoundError:
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                output="Maven not found. Please install Maven to run Java tests.",
            )

        except subprocess.TimeoutExpired:
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                output="Test execution timed out",
            )

        finally:
            # Clean up temp directory
            shutil.rmtree(project_dir, ignore_errors=True)

    def _parse_maven_output(self, output: str, returncode: int = 0) -> TestResult:
        """Parse Maven test output."""
        passed = failed = errors = 0
        failure_details = []

        # Check for compilation errors
        if "COMPILATION ERROR" in output or "cannot find symbol" in output:
            # Extract compilation error details
            error_lines = []
            for line in output.split('\n'):
                if 'error:' in line.lower() or 'cannot find symbol' in line:
                    error_lines.append(line.strip())

            error_msg = '\n'.join(error_lines[:10])  # Limit to first 10 errors
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                output=output,
                failure_details=[{
                    'type': 'CompilationError',
                    'message': error_msg or 'Compilation failed',
                }],
            )

        # Look for summary line
        summary_match = re.search(
            r"Tests run: (\d+), Failures: (\d+), Errors: (\d+)",
            output,
        )
        if summary_match:
            total = int(summary_match.group(1))
            failed = int(summary_match.group(2))
            errors = int(summary_match.group(3))
            passed = total - failed - errors

            # Extract failure details if any
            if failed > 0 or errors > 0:
                failure_details = self._extract_failure_details(output)
        elif returncode != 0:
            # Maven failed but no test summary found - likely build failure
            errors = 1
            failure_details = [{
                'type': 'BuildError',
                'message': 'Maven build failed. Check output for details.',
            }]

        return TestResult(
            passed=passed,
            failed=failed,
            errors=errors,
            output=output,
            failure_details=failure_details,
        )

    def _extract_failure_details(self, output: str) -> list:
        """Extract test failure details from Maven output."""
        details = []

        # Look for test failure patterns
        failure_pattern = re.compile(
            r"(?:FAILURE|ERROR).*?(?:expected|but was|Exception|Error).*",
            re.IGNORECASE | re.DOTALL
        )

        for match in failure_pattern.finditer(output):
            details.append({
                'type': 'TestFailure',
                'message': match.group()[:500],  # Limit message size
            })

        return details

    def _parse_gradle_output(self, output: str) -> TestResult:
        """Parse Gradle test output."""
        passed = failed = errors = 0

        # Parse gradle output
        success_match = re.search(r"(\d+) tests completed", output)
        failure_match = re.search(r"(\d+) failed", output)

        if success_match:
            total = int(success_match.group(1))
            failed = int(failure_match.group(1)) if failure_match else 0
            passed = total - failed

        return TestResult(
            passed=passed,
            failed=failed,
            errors=errors,
            output=output,
        )

    def measure_coverage(
        self,
        test_file: Path,
        source_file: Path,
        timeout: int = 60,
    ) -> tuple[Coverage, TestResult]:
        """Run tests with JaCoCo coverage measurement using Maven.

        Returns:
            Tuple of (Coverage, TestResult) - TestResult contains compilation/test errors.
        """
        if self.dependency_classpath:
            # Closure path: compile/run against the ground-truth target + closure,
            # with JaCoCo measuring line/branch coverage of the TARGET class.
            from docsearch.java_test_executor import JavaTestExecutor

            ground_truth_source = source_file.read_text(encoding="utf-8", errors="replace")
            executor = JavaTestExecutor(
                test_suite_path=str(test_file),
                target_module=source_file.stem,
                repo_path=self.repo_root or str(source_file.parent),
                timeout=timeout,
                dependency_classpath=self.dependency_classpath,
                target_package=self.target_package,
            )
            exec_result = executor.run(ground_truth_source, measure_coverage=True)
            result = self._convert_executor_result(exec_result)
            coverage = Coverage(
                line=exec_result.line_rate,
                branch=exec_result.branch_rate,
                covered_lines=exec_result.covered_lines,
                total_lines=exec_result.total_lines,
            )
            return coverage, result

        # Set up temporary Maven project
        project_dir = self._setup_maven_project(source_file, test_file)

        try:
            # Run maven test with JaCoCo report
            # Use -Dmaven.test.failure.ignore=true to generate coverage even when tests fail
            result = subprocess.run(
                ["mvn", "test", "jacoco:report", "-Dmaven.test.failure.ignore=true"],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=project_dir,
            )

            output = result.stdout + result.stderr

            # Check for compilation errors first
            if "COMPILATION ERROR" in output or "cannot find symbol" in output:
                test_result = self._parse_maven_output(output, result.returncode)
                return Coverage(), test_result

            # Parse test results
            test_result = self._parse_maven_output(output, result.returncode)

            # Parse JaCoCo XML report
            jacoco_report = project_dir / "target" / "site" / "jacoco" / "jacoco.xml"

            if jacoco_report.exists():
                coverage = self._parse_jacoco_report(jacoco_report, source_file)
                return coverage, test_result

            # If no JaCoCo report, tests may have failed before coverage could be measured
            return Coverage(), test_result

        except FileNotFoundError:
            error_result = TestResult(
                passed=0,
                failed=0,
                errors=1,
                output="Maven not found. Please install Maven to run Java tests.",
            )
            return Coverage(), error_result

        except subprocess.TimeoutExpired:
            error_result = TestResult(
                passed=0,
                failed=0,
                errors=1,
                output="Test execution timed out",
            )
            return Coverage(), error_result

        finally:
            # Clean up temp directory
            shutil.rmtree(project_dir, ignore_errors=True)

    # Methods to exclude from coverage calculation (trivial/boilerplate code)
    EXCLUDED_METHODS = {
        "toString", "hashCode", "equals", "compareTo",
        "clone", "finalize",
    }

    # Method name patterns to exclude (getters/setters)
    EXCLUDED_METHOD_PATTERNS = (
        "get", "set", "is", "has",
    )

    def _should_exclude_method(self, method_name: str) -> bool:
        """Check if a method should be excluded from coverage calculation."""
        # Exclude known boilerplate methods
        if method_name in self.EXCLUDED_METHODS:
            return True

        # Exclude simple getters/setters (but not methods that just start with these)
        # Only exclude if it's a short name like getX, setX, isX
        for prefix in self.EXCLUDED_METHOD_PATTERNS:
            if method_name.startswith(prefix) and len(method_name) <= len(prefix) + 15:
                # Check if the rest is a simple property name (starts with uppercase)
                rest = method_name[len(prefix):]
                if rest and rest[0].isupper():
                    return True

        return False

    def _parse_jacoco_report(self, report_path: Path, source_file: Path) -> Coverage:
        """Parse JaCoCo XML report with exclusions for trivial methods."""
        coverage = Coverage()

        try:
            tree = ET.parse(report_path)
            root = tree.getroot()

            total_lines = 0
            covered_lines = 0
            total_branches = 0
            covered_branches = 0
            method_cov_list = []

            # Iterate over classes to filter methods
            for cls in root.findall(".//class"):
                if cls.get("sourcefilename") == source_file.name:
                    # Extract short class name (e.g. "Indicators$Renko" → "Renko")
                    cls_name = cls.get("name", "").split("$")[-1]

                    for method in cls.findall("method"):
                        method_name = method.get("name")

                        # Skip constructors and static initializers
                        if method_name in ("<init>", "<clinit>"):
                            continue

                        # Skip excluded methods (getters, setters, boilerplate)
                        # But only if they're short — large methods named getX
                        # are real logic, not simple getters
                        if self._should_exclude_method(method_name):
                            line_counter = method.find("counter[@type='LINE']")
                            if line_counter is not None:
                                method_lines = (int(line_counter.get("missed", 0))
                                                + int(line_counter.get("covered", 0)))
                                if method_lines <= 5:
                                    continue
                            else:
                                continue

                        # Count coverage for this method
                        m_total = m_covered = 0
                        for counter in method.findall("counter"):
                            counter_type = counter.get("type")
                            missed = int(counter.get("missed", 0))
                            cvd = int(counter.get("covered", 0))

                            if counter_type == "LINE":
                                total_lines += missed + cvd
                                covered_lines += cvd
                                m_total = missed + cvd
                                m_covered = cvd
                            elif counter_type == "BRANCH":
                                total_branches += missed + cvd
                                covered_branches += cvd

                        if m_total > 0:
                            method_cov_list.append({
                                "class": cls_name,
                                "method": method_name,
                                "covered": m_covered,
                                "total": m_total,
                                "pct": m_covered / m_total,
                            })

            # Sort by coverage ascending (lowest first)
            method_cov_list.sort(key=lambda x: (x["pct"], x["total"]))
            coverage.method_coverage = method_cov_list

            # Calculate coverage percentages
            coverage.total_lines = total_lines
            coverage.covered_lines = covered_lines
            if total_lines > 0:
                coverage.line = covered_lines / total_lines

            coverage.total_branches = total_branches
            coverage.covered_branches = covered_branches
            if total_branches > 0:
                coverage.branch = covered_branches / total_branches

            # Get uncovered lines from sourcefile element
            for source in root.findall(".//sourcefile"):
                if source.get("name") == source_file.name:
                    for line in source.findall("line"):
                        if int(line.get("mi", 0)) > 0:
                            coverage.uncovered_lines.append(int(line.get("nr")))
                    break

        except Exception:
            pass

        return coverage

    def generate_test_file(
        self,
        test_cases: list[TestCase],
        source_file: Path,
        imports: list[str],
        class_setup: str = "",
    ) -> str:
        """Generate a complete JUnit5 test file.

        Args:
            test_cases: Test cases to include.
            source_file: Source file being tested.
            imports: Import statements.
            class_setup: Optional class-level setup code (member vars + @BeforeEach).
                When provided, inserted after class declaration before test methods.
        """
        class_name = source_file.stem
        test_class_name = f"{class_name}Test"

        lines = [
            f"// Tests for {class_name}.java",
            "",
            "import org.junit.jupiter.api.Test;",
            "import org.junit.jupiter.api.BeforeEach;",
            "import org.junit.jupiter.api.DisplayName;",
            "import static org.junit.jupiter.api.Assertions.*;",
            "",
        ]

        # Add imports
        for imp in imports:
            if imp not in lines:
                lines.append(imp)

        lines.extend([
            "",
            f"class {test_class_name} {{",
            "",
        ])

        # Add class setup (member variables + @BeforeEach) if provided
        if class_setup:
            indented_setup = "\n".join(
                "    " + line if line.strip() else ""
                for line in class_setup.splitlines()
            )
            lines.append(indented_setup)
            lines.append("")

        # Add test cases
        for test_case in test_cases:
            # Indent test code
            indented_code = "\n".join(
                "    " + line if line.strip() else ""
                for line in test_case.code.splitlines()
            )
            lines.append(indented_code)
            lines.append("")

        lines.append("}")

        return "\n".join(lines)
