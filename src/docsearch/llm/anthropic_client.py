"""Anthropic backend (Claude-4.5-Sonnet etc.)."""
from __future__ import annotations

import anthropic

from docsearch.llm.base import (
    LLMClient, LLMResponse, ToolCall, ToolChatResponse)


class AnthropicClient(LLMClient):
    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self._default_max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def complete(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        seed: int | None = None,
    ) -> LLMResponse:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self._default_max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            raw=resp,
        )

    def generate_with_tools(self, messages, tools, *, temperature: float = 0.0):
        anthropic_tools = [
            {"name": t.get("name"), "description": t.get("description", ""),
             "input_schema": t.get("parameters", {})}
            for t in tools
        ]
        system = None
        convo = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content")
            else:
                convo.append(m)
        kwargs = {"model": self.model, "max_tokens": 8192,
                  "messages": convo, "temperature": temperature}
        if system:
            kwargs["system"] = system
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools
        resp = self._client.messages.create(**kwargs)
        content = ""
        tool_calls = []
        for block in resp.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id, name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {}))
        return ToolChatResponse(
            content=content,
            tool_calls=tool_calls,
            raw_message={"content": [b.model_dump() for b in resp.content]},
        )
