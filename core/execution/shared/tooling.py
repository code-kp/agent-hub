"""
Tests:
- tests/core/execution/shared/test_tooling.py
"""

from __future__ import annotations

import contextvars
from typing import Any, Optional

from core.contracts.tools import ToolDefinition
from core.guardrails import ToolLoopGuardrails
from core.stream.progress import emit_debug_event, emit_thinking_step


def build_guarded_tool_callable(
    tool: ToolDefinition,
    *,
    agent_id: str,
    tool_guardrails: contextvars.ContextVar[Optional[ToolLoopGuardrails]],
):
    callable_tool = tool.build_callable()

    async def guarded_callable(*args: Any, **kwargs: Any) -> Any:
        guardrails = tool_guardrails.get()
        if guardrails is not None:
            block_reason = guardrails.authorize(tool.name, dict(kwargs))
            if block_reason is not None:
                await emit_thinking_step(
                    step_id="tool_guardrails",
                    label="Adjusting the approach",
                    detail=block_reason,
                    state="done",
                    agent_id=agent_id,
                    tool_name=tool.name,
                )
                await emit_debug_event(
                    "tool_guardrail_blocked",
                    agent_id=agent_id,
                    tool_name=tool.name,
                    args=kwargs,
                    reason=block_reason,
                    message=block_reason,
                )
                return {
                    "guardrail_blocked": True,
                    "tool_name": tool.name,
                    "reason": block_reason,
                }
        return await callable_tool(*args, **kwargs)

    guarded_callable.__name__ = callable_tool.__name__
    guarded_callable.__doc__ = callable_tool.__doc__
    guarded_callable.__signature__ = getattr(callable_tool, "__signature__", None)  # type: ignore[attr-defined]
    guarded_callable.__annotations__ = dict(
        getattr(callable_tool, "__annotations__", {})
    )
    return guarded_callable
