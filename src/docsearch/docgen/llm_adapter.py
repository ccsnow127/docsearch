"""Adapter bridging :class:`docsearch.llm.base.LLMClient` to docgen's
``.generate()`` contract.

``ObjectDocGenerator`` / ``RepoDocGenerator`` expect a client exposing
``generate(prompt, *, temperature, system, response_format) -> str``, whereas
:class:`LLMClient` exposes ``complete(prompt, *, temperature, max_tokens, seed)
-> LLMResponse``. This thin wrapper adapts the latter to the former.
"""
from __future__ import annotations


class LLMClientAdapter:
    """Wrap an ``LLMClient`` (``.complete -> LLMResponse``) so it satisfies the
    ``.generate(...) -> str`` contract docgen expects."""

    def __init__(self, client):
        self._client = client

    @property
    def model(self) -> str:
        return getattr(self._client, "model", "")

    def generate(self, prompt: str, *, temperature: float = 0.0,
                 system: "str | None" = None, response_format=None,
                 **kwargs) -> str:
        # The client is single-turn with no system role; fold the
        # system instruction into the prompt. response_format (JSON mode) is a
        # hint only — the JSON shape is already driven by the system prompt, and
        # docgen has its own parse/retry around the returned text.
        full = f"{system}\n\n{prompt}" if system else prompt
        resp = self._client.complete(full, temperature=temperature)
        return getattr(resp, "text", "") or ""
