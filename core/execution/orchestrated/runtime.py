"""
Tests:
- tests/core/execution/orchestrated/test_runtime.py
"""

from __future__ import annotations

from typing import Any

from google.adk.events import Event

import core.execution.shared.adk as runtime_adk
import core.execution.orchestrated.controller as orchestrated_controller
import core.execution.direct.runtime as direct_runtime
import core.execution.shared.usage as runtime_usage
import core.stream.progress as stream_progress


class OrchestratedAgentRuntime(direct_runtime.DirectAgentRuntime):
    def _build_adk_agent(self):
        return orchestrated_controller.build_orchestrated_controller(
            agent_name=self.record.agent_id.replace(".", "_"),
            description=self.definition.description,
            system_prompt=self.definition.system_prompt,
            model_name=self.model_name,
            tool_callables=list(self._tool_callables.values()),
            tool_definitions=tuple(self._tool_definitions.values()),
            execution_config=self.execution,
            agent_hooks=self.hooks,
            before_model_callback=self._before_model_callback,
        )

    async def _handle_runner_event(
        self,
        *,
        stream,
        event: Any,
        message: str,
        resolved_context,
        assistant_buffer: str,
        hook_state,
        stream_output: bool,
        usage_aggregator: runtime_usage.UsageAggregator,
    ) -> str:
        function_calls = list(event.get_function_calls() or [])
        function_responses = list(event.get_function_responses() or [])
        usage_aggregator.record_event(event)

        await self._emit_tool_call_events(
            function_calls=function_calls,
            message=message,
            resolved_context=resolved_context,
            model_hint=runtime_adk.extract_text(event),
        )
        await self._emit_tool_response_events(
            function_responses=function_responses,
        )

        platform_event = _extract_platform_event(event)
        if platform_event is not None:
            await _emit_platform_event(platform_event, agent_id=self.record.agent_id)

        if getattr(event, "author", "") != self.agent.name:
            return assistant_buffer

        text = runtime_adk.extract_text(event)
        if getattr(event, "partial", False) and text:
            assistant_buffer += text
            if stream_output:
                await stream.emit(
                    "assistant_delta",
                    {
                        "agent_id": self.record.agent_id,
                        "text": text,
                    },
                )
            return assistant_buffer

        if event.is_final_response() and (text or assistant_buffer):
            final_text = runtime_adk.merge_streamed_text(
                streamed_text=assistant_buffer,
                final_event_text=text,
            ).strip()
            await stream_progress.emit_thinking_step(
                step_id="answer",
                label="Answer ready",
                detail="The planned work is complete and the final response is ready.",
                state="done",
                agent_id=self.record.agent_id,
            )
            await stream.emit(
                "assistant_message",
                {
                    "agent_id": self.record.agent_id,
                    "text": final_text,
                    "usage": usage_aggregator.summary(),
                },
            )
            return ""

        return assistant_buffer


def _extract_platform_event(event: Event) -> dict[str, Any] | None:
    metadata = getattr(event, "custom_metadata", None) or {}
    platform_event = metadata.get("platform_event")
    if isinstance(platform_event, dict):
        return platform_event
    return None


async def _emit_platform_event(
    platform_event: dict[str, Any], *, agent_id: str
) -> None:
    event_type = str(platform_event.get("type") or "").strip()
    payload = dict(platform_event.get("payload") or {})
    payload.setdefault("agent_id", agent_id)

    if event_type == "thinking_step":
        await stream_progress.emit_thinking_step(
            step_id=str(payload.get("step_id") or "orchestrated"),
            label=str(payload.get("label") or "Working through the request"),
            detail=str(payload.get("detail") or ""),
            state=str(payload.get("state") or "running"),
            agent_id=agent_id,
        )
        return

    if event_type:
        await stream_progress.emit_debug_event(event_type, **payload)
