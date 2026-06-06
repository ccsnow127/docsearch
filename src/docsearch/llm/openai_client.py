"""OpenAI backend (GPT-4o etc.)."""
from __future__ import annotations

from openai import OpenAI

import json

from docsearch.llm.base import (
    LLMClient, LLMResponse, ToolCall, ToolChatResponse)


class OpenAIClient(LLMClient):
    def __init__(self, *, model: str = "gpt-4o", api_key: str | None = None) -> None:
        self.model = model
        self._client = OpenAI(api_key=api_key) if api_key else OpenAI()

    def complete(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        seed: int | None = None,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if seed is not None:
            kwargs["seed"] = seed
        resp = self._client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
            raw=resp,
        )

    def generate_with_tools(self, messages, tools, *, temperature: float = 0.0):
        openai_tools = [{"type": "function", "function": t} for t in tools]
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=openai_tools or None,
            temperature=temperature,
        )
        message = resp.choices[0].message
        tool_calls = []
        for tc in (message.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {"raw": tc.function.arguments}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return ToolChatResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            raw_message=message.model_dump() if hasattr(message, "model_dump") else None,
        )
