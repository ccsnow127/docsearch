"""Detect filesystem / network / time / randomness usage via static AST scan."""
from __future__ import annotations

import ast
from dataclasses import dataclass


_FILESYSTEM_MODULES = {"os", "io", "pathlib", "shutil", "tempfile", "glob", "fileinput"}
_NETWORK_MODULES = {
    "urllib", "urllib2", "http", "httpx", "requests", "socket", "aiohttp",
    "urllib3", "ftplib", "smtplib", "telnetlib",
}
_TIME_MODULES = {"time", "datetime", "calendar"}
_RANDOM_MODULES = {"random", "secrets", "uuid"}

_FILESYSTEM_BUILTINS = {"open"}


@dataclass(frozen=True)
class ExternalDeps:
    """Summary of detected external side effects."""

    filesystem: bool = False
    network: bool = False
    time: bool = False
    randomness: bool = False

    def any(self) -> bool:
        return self.filesystem or self.network or self.time or self.randomness

    def as_human_readable(self) -> str:
        parts: list[str] = []
        if self.filesystem:
            parts.append("filesystem access (use tmp_path / monkeypatch)")
        if self.network:
            parts.append("network I/O (mock via responses / monkeypatch)")
        if self.time:
            parts.append("time-dependent (freeze with monkeypatch or freezegun)")
        if self.randomness:
            parts.append("randomness (seed RNG explicitly)")
        return "\n".join(f"- {p}" for p in parts) if parts else "(none detected)"


def detect_external_deps(source: str) -> ExternalDeps:
    """Scan ``source`` for imports and calls that indicate external deps."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ExternalDeps()

    fs = net = tm = rnd = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                fs |= top in _FILESYSTEM_MODULES
                net |= top in _NETWORK_MODULES
                tm |= top in _TIME_MODULES
                rnd |= top in _RANDOM_MODULES
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".", 1)[0]
            fs |= top in _FILESYSTEM_MODULES
            net |= top in _NETWORK_MODULES
            tm |= top in _TIME_MODULES
            rnd |= top in _RANDOM_MODULES
        elif isinstance(node, ast.Call):
            # Bare ``open(...)`` is a filesystem op.
            if isinstance(node.func, ast.Name) and node.func.id in _FILESYSTEM_BUILTINS:
                fs = True

    return ExternalDeps(filesystem=fs, network=net, time=tm, randomness=rnd)
