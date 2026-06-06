"""Adapt a release LLMClient to the ReAct runtime\'s call shapes.

``agent.runtime.run_agent`` calls ``llm.chat_step(model, system, messages,
tools=..., max_tokens=..., temperature=..., tag=...)`` and expects the result to
expose ``.content``, ``.tool_calls`` (each ``.id``/``.name``/``.arguments``) and
``.raw_message``; it also uses ``llm.complete(prompt, ...).text``. This wraps a
:class:`docsearch.llm.base.LLMClient` (``complete`` + ``generate_with_tools``)
to satisfy both, so run_agent can drive any OpenAI-/Anthropic-backed model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from docsearch.llm.base import LLMClient, ToolChatResponse
from docsearch.llm.factory import build_client


@dataclass(frozen=True)
class Completion:
    text: str


class AgentLLM:
    """Adapts a release ``LLMClient`` to the search / runtime call shapes."""

    def __init__(self, client: LLMClient):
        self._client = client
        self.model = client.model

    def complete(self, prompt: str, *, temperature: float = 0.7,
                 max_tokens: Optional[int] = None,
                 seed: Optional[int] = None) -> Completion:
        return Completion(text=self._client.complete(
            prompt, temperature=temperature).text)

    def chat_step(self, model: str, system: str, messages: list, *,
                  tools: Optional[list] = None, max_tokens: int = 8192,
                  temperature: float = 0.3, tag: str = "agent") -> ToolChatResponse:
        full = [{"role": "system", "content": system}, *messages]
        resp = self._client.generate_with_tools(
            full, tools or [], temperature=temperature)
        if resp.raw_message is None:
            resp.raw_message = {"role": "assistant", "content": resp.content}
        return resp

    def generate(self, prompt: str, *, temperature: float = 0.0,
                 system=None, response_format=None, **kwargs) -> str:
        # docgen's .generate() contract: single-turn str, system folded in.
        full = f"{system}\n\n{prompt}" if system else prompt
        return self._client.complete(full, temperature=temperature).text


def make_agent_llm(model: str = "gpt-5.2-us") -> AgentLLM:
    """Build an :class:`AgentLLM` over a freshly constructed LLM client."""
    return AgentLLM(build_client(model))
