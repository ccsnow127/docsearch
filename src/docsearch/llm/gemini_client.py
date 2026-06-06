"""Google Gemini backend (Gemini-2.5-Flash etc.)."""
from __future__ import annotations

import google.generativeai as genai

from docsearch.llm.base import LLMClient, LLMResponse


class GeminiClient(LLMClient):
    def __init__(self, *, model: str = "gemini-2.5-flash", api_key: str | None = None) -> None:
        if api_key:
            genai.configure(api_key=api_key)
        self.model = model
        self._client = genai.GenerativeModel(model)

    def complete(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        seed: int | None = None,
    ) -> LLMResponse:
        cfg: dict = {"temperature": temperature}
        if max_tokens is not None:
            cfg["max_output_tokens"] = max_tokens
        resp = self._client.generate_content(prompt, generation_config=cfg)
        text = resp.text if hasattr(resp, "text") else ""
        usage = getattr(resp, "usage_metadata", None)
        return LLMResponse(
            text=text,
            input_tokens=getattr(usage, "prompt_token_count", 0) if usage else 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) if usage else 0,
            raw=resp,
        )

    def generate_with_tools(self, messages, tools, *, temperature: float = 0.0):
        raise NotImplementedError(
            "GeminiClient does not implement tool-use; the agent / codegen ReAct "
            "path needs an OpenAI- or Anthropic-backed model (gpt-*/claude-*).")
