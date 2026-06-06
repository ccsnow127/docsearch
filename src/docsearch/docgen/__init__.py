"""
Documentation-generation subsystem (docgen).

This package parses a source tree (or a single file / inline source) into a
structural model, generates per-object behavioral prose with an LLM, and
assembles the project's canonical baseline documentation. All markdown
structure is emitted deterministically from AST data; the LLM contributes only
behavior prose.

Public entry point:
    :class:`RepoDocGenerator` -- walk a repo/file and produce baseline docs.

Shared data model (re-exported for convenience):
    :class:`CodeObject`, :class:`FileStructure`, :class:`RepoStructure`, and the
    object-type constants ``OBJ_CLASS`` / ``OBJ_FUNCTION`` / ``OBJ_METHOD``.
"""

from docsearch.docgen.models import (
    OBJ_CLASS,
    OBJ_FUNCTION,
    OBJ_METHOD,
    CodeObject,
    FileStructure,
    RepoStructure,
)
from docsearch.docgen.repo_doc_generator import RepoDocGenerator

__all__ = [
    "RepoDocGenerator",
    "CodeObject",
    "FileStructure",
    "RepoStructure",
    "OBJ_CLASS",
    "OBJ_FUNCTION",
    "OBJ_METHOD",
]
