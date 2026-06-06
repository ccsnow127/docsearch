"""Validate LLM-generated tests against the reference implementation.

A test is kept only if it passes when executed against the reference
source. Anything that errors or fails is discarded — the reference is
the oracle.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def validate_tests_against_reference(
    reference_source: str,
    candidate_tests: list[str],
    *,
    preamble: str = "",
    timeout: float = 30.0,
) -> list[str]:
    """Return the subset of ``candidate_tests`` that pass on the reference.

    Each test is run in isolation (its own file) so a single bad test
    can't crash the rest of the batch.
    """
    survivors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="docsearch_testval_") as tmp:
        workdir = Path(tmp)
        ref_path = workdir / "_reference.py"
        ref_path.write_text(reference_source)

        for i, test_src in enumerate(candidate_tests):
            test_file = workdir / f"test_candidate_{i}.py"
            test_file.write_text(_render_single_test_file(preamble, test_src))
            if _run_single(test_file, workdir, timeout):
                survivors.append(test_src)
            test_file.unlink(missing_ok=True)

    return survivors


def _render_single_test_file(preamble: str, test_src: str) -> str:
    # Plain concatenation — textwrap.dedent + f-string interpolation
    # mangles multi-line test source when the interpolated value isn't
    # indented to match the surrounding template.
    parts = [
        "import sys, os",
        "sys.path.insert(0, os.path.dirname(__file__))",
        "from _reference import *  # noqa: F401,F403",
        "",
    ]
    if preamble.strip():
        parts.append(preamble.rstrip())
        parts.append("")
    parts.append(test_src.rstrip())
    parts.append("")
    return "\n".join(parts)


def _run_single(test_file: Path, workdir: Path, timeout: float) -> bool:
    """Return True iff the single test passes (exit code 0)."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--tb=no",
        "-q",
        "-p",
        "no:cacheprovider",
        str(test_file),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 0
