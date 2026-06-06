# Language Support

DocSearch runs one pipeline over two languages. Select with `--language`. The
Java toolchain is imported lazily, so the Python path never requires
`javalang`/tree-sitter to be importable.

## At a glance

| Stage | Python | Java |
|---|---|---|
| **Parsing** | `ast` (`docgen/python_parser.py`) | tree-sitter + `javalang` (`docgen/java_parser.py`, `docgen/java_callgraph.py`) |
| **Test generation** | ReAct + pytest + coverage.py | ReAct + Maven + JaCoCo |
| **Code generation** | ReAct agent, import smoke-check | ReAct agent, `javac` compile check |
| **Evaluation** | `PythonEvaluator` + `TestExecutor` (pytest) | `JavaEvaluator` + `JavaTestExecutor` (`javac` + JUnit console launcher) |
| **Closure** | importable package set | dependency classpath |

## Python

**Requirements:** just Python ≥ 3.10 and an API key.

- Entities are functions, methods, and classes parsed with the standard
  library `ast`.
- Tests run through `TestExecutor` (`src/docsearch/test_executor.py`), which
  invokes pytest and attributes each test outcome to an entity.
- The target file is regenerated and imported against its dependency closure so
  the suite runs against real dependencies.

**Example:**

```bash
python -m docsearch.main \
    --module /path/to/repo --target-file pkg/util.py \
    --language python --budget 10 --width 2 \
    --save-artifacts --output-dir runs/myrepo -o runs/myrepo/refined_doc.md
```

## Java

**Requirements:** a JDK (`java`, `javac`) and Maven on `PATH`, in addition to
the Python install. Run `scripts/fetch_libs.sh` once to download the JUnit
Platform Console Launcher and JaCoCo jars into `src/libs/` (binaries, so they
are not committed) — the runner uses them to execute and measure the generated
JUnit suites.

- Entities are parsed with tree-sitter; the call-graph is built by
  `docgen/java_callgraph.py`.
- Test generation targets JUnit; thoroughness is gated by **JaCoCo** line and
  branch coverage of the target class, and a validator enforces that each test
  names and calls a real method/constructor entity (no `Mock`/`Fake`/`Stub`).
- `JavaTestExecutor` (`src/docsearch/java_test_executor.py`) compiles with
  `javac` against the repo's dependency classpath and runs the JUnit console
  launcher.
- Tests are balanced per entity so the φ signal is per method, not a single
  coarse class-level number.

**Example:**

```bash
python -m docsearch.main \
    --module /path/to/java/repo \
    --target-file src/main/java/org/example/Foo.java \
    --language java --budget 10 --width 2 \
    --save-artifacts --output-dir runs/foo -o runs/foo/refined_doc.md
```

!!! note
    `--target-dir` is handy for Java packages: it scopes optimization to one
    sub-path (e.g. `src/main/java/org/jsoup/select`) while still building the
    dependency closure from the whole repository, so everything compiles.

### Why the Java benchmark is a single repo

The bundled Java benchmark is one repository — **jsoup** — verified end-to-end
(`org.jsoup.select.Collector`). That is a deliberate scoping choice, not a
limitation of the search itself:

- The dependency-closure builder currently supports **single-module Maven**
  projects (jsoup is the validated reference). It does **not** yet handle
  multi-module Maven reactors, **Gradle** builds, or **JPMS** (`module-info.java`)
  layouts — for those, the closure (and therefore the test classpath) can't be
  assembled reliably, so test generation has nothing to compile against.
- Rather than ship a pile of Java runs that silently degrade to "no tests →
  vacuous φ=1.0," we ship the one repo we can stand behind. The Python side
  (20 repos) exercises the search across many domains; jsoup demonstrates the
  Java path is real (parsing, JUnit/JaCoCo test-gen, `javac` evaluation).

Extending Java coverage is future work: a closure builder that runs
`mvn install` / per-module `dependency:build-classpath` (and a Gradle path)
would unlock the multi-module repos.

## Adding a language

The pipeline is parameterized by language at each stage — a parser in
`docgen/`, an analyzer in `testgen/react/analyzer/`, and an evaluator/executor
pair. A new language means implementing those contracts; the search loop itself
(`search/loop.py`) is language-agnostic.
