# 🟦 Java language support

*June 2026*

DocSearch now **speaks Java** as well as Python. The pipeline gained a Java
implementation at every stage — it **generates tests**, **generates
documentation**, and **regenerates code** for Java, the same way it does for
Python. Select it with `--language java`.

This is *added compatibility*, not yet parity: it is validated end-to-end on a
single-module Maven repository (jsoup). The dependency-closure builder does not
yet handle multi-module Maven reactors, Gradle, or JPMS (`module-info`), so the
bundled Java benchmark is intentionally a single repo. See
[Language support → why one Java repo](../languages.md#why-the-java-benchmark-is-a-single-repo).

## The whole pipeline, in Java

Every stage gained a Java implementation behind the same contract the Python
path uses:

| Stage | How it works in Java |
|---|---|
| **Parsing** | tree-sitter for structure + a call-graph builder (`docgen/java_parser.py`, `docgen/java_callgraph.py`). |
| **Test generation** | A ReAct agent authors a JUnit suite; thoroughness is gated by **JaCoCo** line/branch coverage of the target class, and a validator requires every test to name and call a real method or constructor (no `Mock`/`Fake`/`Stub` look-alikes). |
| **Code generation** | The ReAct `AgentCodeGenerator` regenerates the class with a `javac` compile check against the repo's dependency classpath. |
| **Evaluation** | `JavaTestExecutor` compiles with `javac` and runs the JUnit console launcher; `JavaEvaluator` attributes each test outcome to its entity to produce the per-method φ. |

Because the work is scoped by the [dependency closure](2026-06-repo-level-input.md),
generated Java compiles and runs against the *real* dependency classes — the way
the code actually behaves, not a mock of it.

## Using it

```bash
python -m docsearch.main \
    --module /path/to/java/repo \
    --target-file src/main/java/org/example/Foo.java \
    --language java \
    --budget 10 --width 2 \
    --save-artifacts --output-dir runs/foo -o runs/foo/refined_doc.md
```

`--target-dir` is convenient for Java packages: scope optimization to one
sub-path (say `src/main/java/org/jsoup/select`) while the closure is still built
from the whole repository, so everything links.

**Requirements:** a JDK (`java`, `javac`) and Maven on `PATH`, in addition to
the Python install.

## Lazy by design

All Java machinery — `javalang`, `JavaTestExecutor`, the tree-sitter grammar —
is imported lazily. The Python path runs without any of it on the import path,
so adding Java cost nothing to existing Python workflows.

## Per-method φ, not per-class

A subtle but important detail: Java tests are **balanced per entity** and the
validator pushes the test-author toward method-level names
(`test_Collector_collect_*`). That keeps the φ signal *per method* rather than
collapsing to a single coarse class-level number — which is what lets the
bi-level search localize a documentation fix to the method that actually needs
it.

→ More in [Language Support → Java](../languages.md#java).
