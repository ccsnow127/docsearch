#!/usr/bin/env bash
# Fetch the Java test-harness JARs into src/libs/ (needed only for --language java).
# The JUnit Platform Console Launcher runs the generated JUnit suites; JaCoCo
# measures line/branch coverage of the target class. These are binaries, so they
# are not committed — run this once before any Java run.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1
LIBS="src/libs"; mkdir -p "$LIBS"
MC="https://repo1.maven.org/maven2"

fetch() { # <url> <dest>
  if [ -f "$LIBS/$2" ]; then echo "  have $2"; return; fi
  echo "  fetching $2 ..."; curl -sSL -o "$LIBS/$2" "$1"
}

fetch "$MC/org/junit/platform/junit-platform-console-standalone/1.9.0/junit-platform-console-standalone-1.9.0.jar" \
      "junit-platform-console-standalone-1.9.0.jar"
fetch "$MC/org/jacoco/org.jacoco.agent/0.8.11/org.jacoco.agent-0.8.11-runtime.jar" "jacocoagent.jar"
fetch "$MC/org/jacoco/org.jacoco.cli/0.8.11/org.jacoco.cli-0.8.11-nodeps.jar"       "jacococli.jar"

echo "Java libs ready in $LIBS:"; ls -1 "$LIBS"
