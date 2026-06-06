"""The director loop — one generic agent runtime, used by both roles.

A deliberately minimal director loop (philosophy: minimal prescribed workflow,
rich primitives, the agent decides). It owns nothing domain-specific: it
assembles a system prompt from
the workspace, calls the LLM with the tool schemas, executes the returned tool
calls against the real filesystem, feeds the results back, and loops — bounded
by a turn budget and a same-tool circuit breaker, with every event appended to a
JSONL session log (the agent's durable, auditable memory).

The LLM call is the injected client's ``chat_step`` (the model is
stateless; this loop owns the ``messages`` history). The role (generation vs
developer) is entirely determined by the ``role_base`` prompt, the ``workspace``
contents, and which feedback ``Tool`` the driver registers — the loop is the
same.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from docsearch.agent.tools import tool_schemas


# --------------------------------------------------------------------------- #
# System-prompt assembly — the filesystem IS the agent's identity/memory
# --------------------------------------------------------------------------- #
def assemble_system(role_base: str, workspace: str) -> str:
    """Role base prompt + the workspace's AGENTS.md (project memory), if present.

    Builds the system prompt: a short hardcoded role template plus
    the on-disk ``AGENTS.md`` injected as project context. The agent can edit its
    own ``AGENTS.md`` like any file, so memory persists across runs.
    """
    parts = [role_base.strip()]
    agents_md = os.path.join(workspace, "AGENTS.md")
    if os.path.isfile(agents_md):
        with open(agents_md, encoding="utf-8", errors="replace") as f:
            txt = f.read().strip()
        if txt:
            parts.append("## Project context (AGENTS.md)\n" + txt)
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- #
# Session log — append-only JSONL (durable memory + audit)
# --------------------------------------------------------------------------- #
def _append_event(session_path: "str | None", event: dict) -> None:
    if not session_path:
        return
    event = {"t": time.time(), **event}
    os.makedirs(os.path.dirname(session_path) or ".", exist_ok=True)
    with open(session_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _safe_done_check(fn, workspace):
    """Run a done_check, treating any error as 'accept' so a buggy check can
    never trap the agent in an infinite loop. Returns (ok: bool, message: str)."""
    try:
        ok, msg = fn(workspace)
        return bool(ok), str(msg)
    except Exception as exc:
        return True, f"(done_check errored: {exc})"


# --------------------------------------------------------------------------- #
# The result
# --------------------------------------------------------------------------- #
@dataclass
class AgentResult:
    turns: int
    stop_reason: str
    final_text: str
    tool_calls: int
    messages: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #
def run_agent(*, llm, model, workspace: str, role_base: str, task: str,
              tools: "dict", budget: int = 24, temperature: float = 0.3,
              tag: str = "agent", session_path: "str | None" = None,
              max_same_tool: int = 10, done_check=None,
              max_no_act: int = 3) -> AgentResult:
    """Run the director loop until the agent calls ``done`` or a bound trips.

    Args:
        llm:        an LLMClient exposing ``chat_step``.
        model:      model id.
        workspace:  the agent's working directory (action surface + memory).
        role_base:  the short role system prompt (generation vs developer).
        task:       the kickoff user message.
        tools:      ``{name: Tool}`` — the rich primitives + the role feedback
                    tool (+ ``done``).
        budget:     max LLM turns.
        session_path: where to append the JSONL event log (None = no log).
        max_same_tool: circuit breaker — stop after this many identical-tool
                    calls in a row (a stuck agent).
        done_check: optional ``callable(workspace) -> (ok: bool, message: str)``.
                    When set, ``done`` (and an implicit stop with no tool call)
                    is ACCEPTED only if ``ok``; otherwise ``message`` is fed back
                    and the loop continues. Use it to enforce a real termination
                    contract — e.g. "all tests pass". budget / circuit_breaker
                    still hard-stop as safety exits (reported as not-done).
        max_no_act: with a done_check, give up after this many consecutive
                    no-tool-call turns that still fail the check.

    Returns:
        AgentResult (turns used, why it stopped, last assistant text, #tool calls).
    """
    system = assemble_system(role_base, workspace)
    schemas = tool_schemas(tools.values())
    messages: list = [{"role": "user", "content": task}]
    _append_event(session_path, {"kind": "task", "text": task})

    final_text = ""
    total_tool_calls = 0
    last_tool = None
    same_streak = 0
    no_act_streak = 0
    stop_reason = "budget"

    turn = 0
    while turn < budget:
        try:
            step = llm.chat_step(model, system, messages, tools=schemas,
                                 max_tokens=8192, temperature=temperature, tag=tag)
        except Exception as exc:  # a transient LLM failure must not crash the run
            _append_event(session_path, {"kind": "error", "text": str(exc)})
            stop_reason = "llm_error"
            break

        messages.append(step.raw_message)
        if step.content:
            final_text = step.content
            _append_event(session_path, {"kind": "assistant", "text": step.content})

        if not step.tool_calls:
            if done_check is not None:
                ok, msg = _safe_done_check(done_check, workspace)
                if ok:
                    stop_reason = "done"
                    break
                no_act_streak += 1
                if no_act_streak >= max_no_act:
                    stop_reason = "stuck_not_done"
                    _append_event(session_path, {"kind": "stop",
                                  "reason": "stuck_not_done", "detail": msg[:300]})
                    break
                messages.append({"role": "user", "content":
                    "You stopped before finishing. " + msg + " Make a tool call "
                    "to fix the remaining failures, then call done."})
                turn += 1
                continue
            stop_reason = "no_tool_calls"
            break
        no_act_streak = 0

        stop = False
        for tc in step.tool_calls:
            name = tc.name
            args = tc.arguments if isinstance(tc.arguments, dict) else {}
            total_tool_calls += 1
            _append_event(session_path, {"kind": "tool_call", "tool": name, "args": args})

            if name == "done":
                ok, msg = ((True, "ok") if done_check is None
                           else _safe_done_check(done_check, workspace))
                if ok:
                    final_text = str(args.get("summary") or final_text or "done")
                    messages.append({"role": "tool", "tool_call_id": tc.id,
                                     "content": "ok — verified."})
                    stop = True
                    stop_reason = "done"
                else:
                    # Reject the stop: the contract isn't met. Feed back what is
                    # still wrong and keep the loop going.
                    messages.append({"role": "tool", "tool_call_id": tc.id,
                                     "content": "NOT done yet. " + msg})
                    _append_event(session_path, {"kind": "done_rejected",
                                                 "detail": msg[:300]})
                continue

            tool = tools.get(name)
            if tool is None:
                result = f"unknown tool '{name}'"
            else:
                try:
                    result = tool.run(workspace, args)
                except Exception as exc:
                    result = f"tool error: {exc}"
            result = str(result)
            _append_event(session_path, {"kind": "tool_result", "tool": name,
                                         "result": result[:4000]})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

            # Circuit breaker: count identical-tool streaks.
            if name == last_tool:
                same_streak += 1
            else:
                same_streak = 1
                last_tool = name

        turn += 1
        if stop:
            break
        if same_streak >= max_same_tool:
            stop_reason = "circuit_breaker"
            _append_event(session_path, {"kind": "stop", "reason": "circuit_breaker",
                                         "tool": last_tool})
            break

    _append_event(session_path, {"kind": "stop", "reason": stop_reason, "turns": turn})
    return AgentResult(turns=turn, stop_reason=stop_reason, final_text=final_text,
                       tool_calls=total_tool_calls, messages=messages)
