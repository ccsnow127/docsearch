"""ReAct, coverage-gated test generator.

A subpackage alongside the lighter entity-level ``testgen`` loop. Java support
is lazy-loaded (javalang, JavaTestExecutor) so the Python path imports without
those dependencies.
"""
from docsearch.testgen.react.react_loop import ReactTestGenerator
from docsearch.testgen.react.config import TestGeneratorConfig

__all__ = ["ReactTestGenerator", "TestGeneratorConfig"]
