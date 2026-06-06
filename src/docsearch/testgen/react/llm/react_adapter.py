"""A ``chat_step`` LLM adapter for the test-generation ReAct agent.

The ReAct runtime (agent/runtime.py) drives the model via
``llm.chat_step(model, system, messages, tools=..., max_tokens=...,
temperature=..., tag=...)`` and expects a step with ``.content``,
``.tool_calls`` (each with ``.id``/``.name``/``.arguments``) and
``.raw_message``.

The search package already ships an adapter with exactly that shape
(:class:`docsearch.search.llm_adapter.SearchLLM`), built over
:class:`docsearch.llm_client.LLMClient`. Rather than duplicate it, this module
re-exports it under test-generation-flavored names so the test_generator
package owns its own entry point without leaking provider details.
"""
from __future__ import annotations

from docsearch.llm.agent_adapter import AgentLLM as TestGenLLM
from docsearch.llm.agent_adapter import make_agent_llm as make_search_llm


def make_testgen_llm(model: str = "gpt-5.2-us") -> TestGenLLM:
    """Build a :class:`TestGenLLM` over a freshly constructed project client."""
    return make_search_llm(model)


__all__ = ["TestGenLLM", "make_testgen_llm"]
