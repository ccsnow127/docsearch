"""Build an LLM backend from a model-name string."""
from __future__ import annotations

from docsearch.llm.base import LLMClient


def build_client(model: str, *, api_key: str | None = None, **kwargs) -> LLMClient:
    """Construct a backend client for ``model``."""
    m = model.lower()
    if m.startswith(("gpt-", "o1", "o3", "openai/")):
        from docsearch.llm.openai_client import OpenAIClient
        return OpenAIClient(model=model, api_key=api_key)
    if m.startswith("claude"):
        from docsearch.llm.anthropic_client import AnthropicClient
        return AnthropicClient(model=model, api_key=api_key)
    if m.startswith("gemini"):
        from docsearch.llm.gemini_client import GeminiClient
        return GeminiClient(model=model, api_key=api_key)
    raise ValueError(
        f"unknown model '{model}'. Supported prefixes: gpt-, claude-, gemini-."
    )
