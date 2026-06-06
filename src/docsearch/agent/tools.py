"""Rich filesystem primitives — the agent's action surface (the tool layer).

The agent acts on a WORKSPACE directory through generic coding-agent tools:
``read_file`` / ``write_file`` / ``edit_file`` / ``list_dir`` / ``grep`` /
``bash`` (+ the role's feedback tool and ``done``). The same files are both the
agent's memory (it reads AGENTS.md, the module under test) and its action
surface (it edits the artifact). Every file/shell access is confined to the
workspace — path operations are realpath-checked against the workspace root and
``bash`` runs with ``cwd=workspace`` — a per-project sandbox.

A :class:`Tool` is the uniform contract the runtime dispatches: ``name`` +
``description`` + ``input_schema`` (Anthropic-style, for ``chat_step``) +
``run(workspace, args) -> str``. Role-specific tools (``measure`` / ``run_eval``)
are built elsewhere as closures over their backend and registered the same way.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Callable


# --------------------------------------------------------------------------- #
# The uniform tool contract
# --------------------------------------------------------------------------- #
@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    run: Callable          # (workspace: str, args: dict) -> str
    kind: str = "fs"       # "fs" | "feedback" | "control"


def tool_schemas(tools) -> list:
    """Render tools into the chat_step tool list (Anthropic-style)."""
    return [
        {"name": t.name, "description": t.description,
         "input_schema": t.input_schema or {"type": "object", "properties": {}}}
        for t in tools
    ]


# --------------------------------------------------------------------------- #
# Workspace confinement
# --------------------------------------------------------------------------- #
def _resolve(workspace: str, path: str) -> str:
    """Resolve ``path`` under ``workspace``; raise if it escapes the workspace."""
    base = os.path.realpath(workspace)
    full = os.path.realpath(os.path.join(base, path or "."))
    if full != base and not full.startswith(base + os.sep):
        raise ValueError(f"path {path!r} escapes the workspace")
    return full


_MAX_OUT = 8000


def _cap(text: str, note: str = "") -> str:
    if len(text) > _MAX_OUT:
        return text[:_MAX_OUT] + f"\n... (truncated{(' ' + note) if note else ''})"
    return text


# --------------------------------------------------------------------------- #
# The primitive implementations
# --------------------------------------------------------------------------- #
def _read_file(workspace: str, args: dict) -> str:
    path = str(args.get("path", "")).strip()
    if not path:
        return "read_file needs a 'path'"
    full = _resolve(workspace, path)
    if not os.path.isfile(full):
        return f"(no such file: {path})"
    with open(full, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    cap = 800
    body = "\n".join(f"{i + 1}\t{ln}" for i, ln in enumerate(lines[:cap]))
    if len(lines) > cap:
        body += f"\n... ({len(lines) - cap} more lines; use grep/bash to scope)"
    return body or "(empty file)"


def _write_file(workspace: str, args: dict) -> str:
    path = str(args.get("path", "")).strip()
    content = args.get("content", "")
    if not path:
        return "write_file needs a 'path'"
    if not isinstance(content, str):
        return "write_file 'content' must be a string"
    full = _resolve(workspace, path)
    os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    return f"wrote {path} ({len(content)} bytes, {content.count(chr(10)) + 1} lines)"


def _edit_file(workspace: str, args: dict) -> str:
    path = str(args.get("path", "")).strip()
    old = args.get("old_string", "")
    new = args.get("new_string", "")
    if not path:
        return "edit_file needs a 'path'"
    if not isinstance(old, str) or not old:
        return "edit_file needs a non-empty 'old_string'"
    if not isinstance(new, str):
        return "edit_file 'new_string' must be a string"
    full = _resolve(workspace, path)
    if not os.path.isfile(full):
        return f"(no such file: {path})"
    with open(full, encoding="utf-8") as f:
        txt = f.read()
    n = txt.count(old)
    if n == 0:
        return f"old_string not found in {path} — read_file it first and copy exact text"
    if n > 1:
        return f"old_string is not unique in {path} ({n} matches) — add surrounding context"
    with open(full, "w", encoding="utf-8") as f:
        f.write(txt.replace(old, new, 1))
    return f"edited {path} (1 replacement)"


def _list_dir(workspace: str, args: dict) -> str:
    full = _resolve(workspace, str(args.get("path", ".")))
    if not os.path.isdir(full):
        return f"(not a directory: {args.get('path', '.')})"
    out = []
    for name in sorted(os.listdir(full)):
        p = os.path.join(full, name)
        out.append(f"{'dir ' if os.path.isdir(p) else 'file'}  {name}")
    return "\n".join(out) or "(empty directory)"


def _grep(workspace: str, args: dict) -> str:
    pattern = str(args.get("pattern", ""))
    path = str(args.get("path", "."))
    if not pattern:
        return "grep needs a 'pattern'"
    full = _resolve(workspace, path)
    base = os.path.realpath(workspace) + os.sep
    try:
        r = subprocess.run(["grep", "-rnE", pattern, full],
                           capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError) as e:
        return f"grep error: {e}"
    out = "\n".join(ln.replace(base, "") for ln in r.stdout.splitlines()[:200])
    return _cap(out, "more matches") or "(no matches)"


def _bash(workspace: str, args: dict) -> str:
    cmd = str(args.get("command", "")).strip()
    if not cmd:
        return "bash needs a 'command'"
    try:
        r = subprocess.run(cmd, shell=True, cwd=os.path.realpath(workspace),
                           capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "command timed out after 120s"
    out = (r.stdout or "")
    if r.stderr:
        out += ("\n[stderr]\n" + r.stderr)
    out = out.strip()
    return _cap(out, f"exit={r.returncode}") or f"(no output, exit={r.returncode})"


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def default_tools() -> "dict[str, Tool]":
    """The role-independent rich primitives + the ``done`` control tool.

    The driver adds the role's feedback tool (``measure`` / ``run_eval``) on top.
    """
    t = {}

    def reg(tool: Tool):
        t[tool.name] = tool

    reg(Tool("read_file",
             "Read a file in the workspace (line-numbered). Use it to inspect "
             "the module under test, the current test_suite.py, AGENTS.md, or "
             "any harness source before editing.",
             {"type": "object", "properties": {"path": {"type": "string"}},
              "required": ["path"]}, _read_file))
    reg(Tool("write_file",
             "Create or OVERWRITE a file with full content. Use for writing a "
             "fresh test_suite.py; prefer edit_file for small changes.",
             {"type": "object",
              "properties": {"path": {"type": "string"},
                             "content": {"type": "string"}},
              "required": ["path", "content"]}, _write_file))
    reg(Tool("edit_file",
             "Replace one unique occurrence of old_string with new_string in a "
             "file (exact match). The safe way to make a small change.",
             {"type": "object",
              "properties": {"path": {"type": "string"},
                             "old_string": {"type": "string"},
                             "new_string": {"type": "string"}},
              "required": ["path", "old_string", "new_string"]}, _edit_file))
    reg(Tool("list_dir",
             "List the entries of a directory in the workspace.",
             {"type": "object", "properties": {"path": {"type": "string"}}},
             _list_dir))
    reg(Tool("grep",
             "Search files for an (extended) regex — e.g. find a class/def in "
             "the module under test to learn its REAL signature instead of "
             "guessing. Returns file:line:match.",
             {"type": "object",
              "properties": {"pattern": {"type": "string"},
                             "path": {"type": "string"}},
              "required": ["pattern"]}, _grep))
    reg(Tool("bash",
             "Run a shell command with cwd=workspace (python, grep, ls, etc.). "
             "Use it for anything the dedicated tools don't cover. Confined to "
             "the workspace directory.",
             {"type": "object", "properties": {"command": {"type": "string"}},
              "required": ["command"]}, _bash))
    reg(Tool("done",
             "Stop. Call this when the feedback tool no longer improves (or you "
             "have concluded no further change helps). Optionally summarise.",
             {"type": "object", "properties": {"summary": {"type": "string"}}},
             lambda ws, a: "ok", kind="control"))
    return t
