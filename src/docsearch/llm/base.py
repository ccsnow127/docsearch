"""Abstract LLM client interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw: object | None = None  # backend-specific response object, if any


@dataclass
class ToolCall:
    """A single tool call requested by the model."""
    id: str
    name: str
    arguments: dict


@dataclass
class ToolChatResponse:
    """One tool-enabled chat turn, in the shape the ReAct runtime expects.

    Mutable on purpose: the agent adapter backfills ``raw_message`` when a
    backend does not supply one.
    """
    content: str = ""
    tool_calls: list = field(default_factory=list)
    raw_message: dict | None = None


class LLMClient(ABC):
    model: str

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        seed: int | None = None,
    ) -> LLMResponse:
        ...

    def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        temperature: float = 0.0,
    ) -> "ToolChatResponse":
        """One tool-enabled chat turn. Overridden by backends that support it
        (OpenAI, Anthropic). The default raises so an unsupported backend fails
        loudly instead of silently dropping the tools."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support tool-use."
        )
