from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Mapping, Optional, Sequence
from uuid import uuid4

from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

import core.contracts.agent as contracts_agent
import core.contracts.models as contracts_models
import core.execution.shared.adk as shared_adk
import core.execution.shared.models as shared_models
import core.stream.progress as stream_progress


if TYPE_CHECKING:
    from core.platform import AgentPlatform


SMART_AGENT_ID = "smart"
SMART_AGENT_NAME = "Team Mode"
SMART_AGENT_DESCRIPTION = "Coordinates a response across the selected agents and returns only routed-agent output."

DEFAULT_MODEL = "gemini-2.0-flash"
ROUTER_TIMEOUT_SECONDS = 20.0
MAX_SMART_ITERATIONS = 4
ROUTING_DEBUG_EVENT_TYPES = {
    "tool_selection_reason",
    "tool_started",
    "tool_completed",
    "skill_context_selected",
    "model_started",
}


class SmartDecision(BaseModel):
    action: Literal["delegate", "finalize"]
    rationale: str = Field(default="")
    agent_id: str = Field(default="")
    mode: Optional[str] = None
    goal: str = Field(default="")
    answer: str = Field(default="")


@dataclass(frozen=True)
class RoutedAgentStep:
    agent_id: str
    mode: str
    goal: str
    rationale: str


@dataclass(frozen=True)
class RoutedAgentResult:
    agent_id: str
    agent_name: str
    mode: str
    goal: str
    rationale: str
    text: str
    usage: dict[str, Any] | None = None
    streamed_output: bool = False


class SmartAgentRuntime:
    def __init__(
        self,
        platform: AgentPlatform,
        *,
        model_name_override: str | None = None,
        timeout_seconds: float = ROUTER_TIMEOUT_SECONDS,
    ) -> None:
        self.platform = platform
        self.model_name_override = str(model_name_override or "").strip()
        self.model_name = self._resolve_model_name(self.model_name_override)
        self.resolved_model = shared_models.resolve_model(self.model_name)
        self.timeout_seconds = timeout_seconds

    def _resolve_model_name(self, model_name_override: str | None = None) -> str:
        requested_model = contracts_models.normalize_model_reference(
            model_name_override,
            model_backend=os.getenv("MODEL_BACKEND"),
        )
        if requested_model:
            return requested_model

        env_model = contracts_models.normalize_model_reference(
            os.getenv("MODEL_NAME"),
            model_backend=os.getenv("MODEL_BACKEND"),
        )
        if env_model:
            return env_model

        return DEFAULT_MODEL

    async def stream_chat(
        self,
        message: str,
        user_id: str,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        history: Optional[list[dict[str, Any]]] = None,
        team_agent_ids: Optional[Sequence[str]] = None,
        stream: bool = True,
    ):
        active_session_id = session_id or "team-{value}".format(value=uuid4())
        event_stream = stream_progress.EventStream()
        asyncio.create_task(
            self._run_chat(
                stream=event_stream,
                message=message,
                user_id=user_id,
                session_id=active_session_id,
                conversation_id=conversation_id,
                history=history or [],
                team_agent_ids=team_agent_ids or [],
                stream_output=stream,
            )
        )
        return active_session_id, event_stream.sse_messages()

    async def _run_chat(
        self,
        *,
        stream: stream_progress.EventStream,
        message: str,
        user_id: str,
        session_id: str,
        conversation_id: Optional[str],
        history: list[dict[str, Any]],
        team_agent_ids: Sequence[str],
        stream_output: bool,
    ) -> None:
        stream_token = stream_progress.bind_progress_stream(stream)
        try:
            selected_team = [
                agent_id.strip()
                for agent_id in team_agent_ids
                if str(agent_id or "").strip()
            ]
            await stream.emit(
                "run_started",
                {
                    "agent_id": SMART_AGENT_ID,
                    "session_id": session_id,
                    "user_id": user_id,
                    "message": (
                        "Selecting the best agent from the chosen team."
                        if selected_team
                        else "Selecting the best agent for this request."
                    ),
                },
            )
            candidates = self._routing_candidates(selected_team)
            if not candidates:
                await self._emit_terminal_error(
                    stream=stream,
                    session_id=session_id,
                    message=(
                        "Team Mode needs at least one available selected agent."
                        if selected_team
                        else "No defined agents are available to take this request."
                    ),
                )
                return

            results: list[RoutedAgentResult] = []
            usages: list[dict[str, Any]] = []
            saw_streamed_output = False

            for iteration in range(1, MAX_SMART_ITERATIONS + 1):
                await stream_progress.emit_thinking_step(
                    step_id="smart_decision_{index}".format(index=iteration),
                    label="Selecting the next agent",
                    detail=(
                        "Checking whether the answer is ready or whether another agent should take the next step."
                    ),
                    state="running",
                    agent_id=SMART_AGENT_ID,
                )
                decision = await self._decide_next_step(
                    message=message,
                    history=history,
                    candidates=candidates,
                    results=results,
                )

                if decision.action == "finalize":
                    final_text = str(decision.answer or "").strip()
                    if not final_text:
                        final_text = self._compose_fallback_answer(results)
                    if not final_text:
                        await self._emit_terminal_error(
                            stream=stream,
                            session_id=session_id,
                            message="Could not finalize an answer from the available evidence.",
                        )
                        return

                    await stream_progress.emit_thinking_step(
                        step_id="smart_decision_{index}".format(index=iteration),
                        label="Finalizing the answer",
                        detail=str(decision.rationale or "").strip()
                        or "The gathered evidence is sufficient to answer directly.",
                        state="done",
                        agent_id=SMART_AGENT_ID,
                    )
                    if stream_output and not saw_streamed_output:
                        await stream.emit(
                            "assistant_delta",
                            {
                                "agent_id": SMART_AGENT_ID,
                                "text": final_text,
                            },
                        )
                    await stream.emit(
                        "assistant_message",
                        {
                            "agent_id": SMART_AGENT_ID,
                            "text": final_text,
                            "usage": _merge_usage_payloads(usages),
                        },
                    )
                    await stream.emit(
                        "run_completed",
                        {
                            "agent_id": SMART_AGENT_ID,
                            "session_id": session_id,
                            "message": "Completed the coordinated response.",
                        },
                    )
                    return

                step = self._step_from_decision(decision, candidates=candidates)
                candidate = self._candidate_lookup(step.agent_id, candidates)

                await stream_progress.emit_thinking_step(
                    step_id="smart_delegate_{index}".format(index=iteration),
                    label="Using {name}".format(
                        name=str(candidate.get("name") or step.agent_id)
                    ),
                    detail=step.rationale
                    or step.goal
                    or "Handing this part of the task to the most relevant agent.",
                    state="running",
                    agent_id=SMART_AGENT_ID,
                )
                result = await self._run_routed_agent(
                    stream=stream,
                    user_message=message,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    history=history,
                    step_index=iteration,
                    step=step,
                    candidates=candidates,
                    previous_results=results,
                    stream_output=stream_output,
                )
                usages.append(result.usage or {})
                results.append(result)
                saw_streamed_output = saw_streamed_output or result.streamed_output

                await stream_progress.emit_thinking_step(
                    step_id="smart_delegate_{index}".format(index=iteration),
                    label="{name} finished".format(name=result.agent_name),
                    detail=(
                        "Captured the delegated output."
                        if result.text.strip()
                        else "The delegated agent did not return a usable output."
                    ),
                    state="done" if result.text.strip() else "error",
                    agent_id=SMART_AGENT_ID,
                )

            fallback_answer = self._compose_fallback_answer(results)
            if not fallback_answer:
                await self._emit_terminal_error(
                    stream=stream,
                    session_id=session_id,
                    message="Reached the routing limit without enough evidence to answer.",
                )
                return

            await stream_progress.emit_thinking_step(
                step_id="smart_limit",
                label="Reached the routing limit",
                detail="Finalizing from the outputs already gathered instead of assigning another agent.",
                state="done",
                agent_id=SMART_AGENT_ID,
            )
            if stream_output and not saw_streamed_output:
                await stream.emit(
                    "assistant_delta",
                    {
                        "agent_id": SMART_AGENT_ID,
                        "text": fallback_answer,
                    },
                )
            await stream.emit(
                "assistant_message",
                {
                    "agent_id": SMART_AGENT_ID,
                    "text": fallback_answer,
                    "usage": _merge_usage_payloads(usages),
                },
            )
            await stream.emit(
                "run_completed",
                {
                    "agent_id": SMART_AGENT_ID,
                    "session_id": session_id,
                    "message": "Completed the coordinated response.",
                },
            )
        except Exception as exc:
            await stream_progress.emit_thinking_step(
                step_id="smart_failure",
                label="Agent coordination failed",
                detail=str(exc) or "The agent handoff loop could not complete.",
                state="error",
                agent_id=SMART_AGENT_ID,
            )
            await self._emit_terminal_error(
                stream=stream,
                session_id=session_id,
                message=str(exc) or "The agent handoff loop could not complete.",
            )
        finally:
            stream_progress.reset_progress_stream(stream_token)
            await stream.close()

    async def _emit_terminal_error(
        self,
        *,
        stream: stream_progress.EventStream,
        session_id: str,
        message: str,
    ) -> None:
        await stream.emit(
            "error",
            {
                "agent_id": SMART_AGENT_ID,
                "session_id": session_id,
                "message": message,
                "error": "team_mode_error",
            },
        )
        await stream.emit(
            "assistant_message",
            {
                "agent_id": SMART_AGENT_ID,
                "text": message,
            },
        )

    async def _decide_next_step(
        self,
        *,
        message: str,
        history: Sequence[Mapping[str, Any]],
        candidates: Sequence[Mapping[str, Any]],
        results: Sequence[RoutedAgentResult],
    ) -> SmartDecision:
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                decision = await self._request_decision(
                    message=message,
                    history=history,
                    candidates=candidates,
                    results=results,
                )
                return self._normalize_decision(decision, candidates=candidates)
            except Exception as exc:
                last_error = exc

        fallback_answer = self._compose_fallback_answer(results)
        if fallback_answer:
            return SmartDecision(
                action="finalize",
                rationale=(
                    "Finalizing from the collected agent outputs because the planner did not return a usable next step."
                ),
                answer=fallback_answer,
            )

        raise last_error or ValueError("Could not decide which agent should act next.")

    async def _request_decision(
        self,
        *,
        message: str,
        history: Sequence[Mapping[str, Any]],
        candidates: Sequence[Mapping[str, Any]],
        results: Sequence[RoutedAgentResult],
    ) -> SmartDecision:
        session_service = InMemorySessionService()
        session_id = "agent-router-{value}".format(value=uuid4())
        user_id = "agent-router"
        created = session_service.create_session(
            app_name="agent_hub_agent_router",
            user_id=user_id,
            session_id=session_id,
        )
        if asyncio.iscoroutine(created):
            await created

        agent = shared_adk.create_llm_agent(
            agent_id="agent_router",
            model=self.resolved_model.adk_model,
            instruction=_decision_instruction(),
            tool_callables=[],
            before_model_callback=lambda *_args, **_kwargs: None,
        )
        runner = shared_adk.create_runner(
            agent=agent,
            session_service=session_service,
            app_name="agent_hub_agent_router",
        )

        generated = ""
        async with asyncio.timeout(self.timeout_seconds):
            async for event in shared_adk.stream_runner_events(
                runner=runner,
                user_id=user_id,
                session_id=session_id,
                new_message=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text=_decision_message(
                                message=message,
                                history=history,
                                candidates=candidates,
                                results=results,
                            )
                        )
                    ],
                ),
                stream_output=False,
            ):
                text = shared_adk.extract_text(event)
                if getattr(event, "partial", False) and text:
                    generated += text
                elif event.is_final_response() and text:
                    generated = shared_adk.merge_streamed_text(
                        streamed_text=generated,
                        final_event_text=text,
                    )

        payload = _extract_json_payload(generated)
        return SmartDecision.model_validate(payload)

    def _normalize_decision(
        self,
        decision: SmartDecision,
        *,
        candidates: Sequence[Mapping[str, Any]],
    ) -> SmartDecision:
        if decision.action == "finalize":
            return SmartDecision(
                action="finalize",
                rationale=_compact_text(
                    decision.rationale or "The available evidence is sufficient.",
                    limit=220,
                ),
                answer=str(decision.answer or "").strip(),
            )

        candidate = self._candidate_lookup(decision.agent_id, candidates)
        runtime_modes = list(candidate.get("runtime_modes") or ["direct"])
        default_mode = str(candidate.get("default_mode") or "direct").strip()
        requested_mode = contracts_agent.normalize_runtime_mode(
            decision.mode or default_mode
        )
        if requested_mode not in runtime_modes:
            requested_mode = default_mode if default_mode in runtime_modes else "direct"

        return SmartDecision(
            action="delegate",
            rationale=_compact_text(
                decision.rationale
                or decision.goal
                or str(
                    candidate.get("description")
                    or "Selected from the defined agent catalog."
                ),
                limit=220,
            ),
            agent_id=str(candidate.get("id") or "").strip(),
            mode=requested_mode,
            goal=_compact_text(
                decision.goal
                or "Contribute the next part of the answer that best matches this agent.",
                limit=220,
            ),
        )

    def _step_from_decision(
        self,
        decision: SmartDecision,
        *,
        candidates: Sequence[Mapping[str, Any]],
    ) -> RoutedAgentStep:
        candidate = self._candidate_lookup(decision.agent_id, candidates)
        return RoutedAgentStep(
            agent_id=str(candidate.get("id") or "").strip(),
            mode=str(
                decision.mode or candidate.get("default_mode") or "direct"
            ).strip(),
            goal=str(decision.goal or "").strip(),
            rationale=str(decision.rationale or "").strip(),
        )

    async def _run_routed_agent(
        self,
        *,
        stream: stream_progress.EventStream,
        user_message: str,
        user_id: str,
        conversation_id: Optional[str],
        history: Sequence[Mapping[str, Any]],
        step_index: int,
        step: RoutedAgentStep,
        candidates: Sequence[Mapping[str, Any]],
        previous_results: Sequence[RoutedAgentResult],
        stream_output: bool,
    ) -> RoutedAgentResult:
        candidate = self._candidate_lookup(step.agent_id, candidates)
        resolved_agent_id, resolved_mode, runtime = self.platform.resolve_runtime(
            step.agent_id,
            mode=step.mode,
            model_name=self.model_name_override or None,
        )
        delegated_message = self._build_delegated_message(
            user_message=user_message,
            step_index=step_index,
            step=step,
            previous_results=previous_results,
        )
        _delegated_session_id, raw_stream = await runtime.stream_chat(
            message=delegated_message,
            user_id=user_id,
            session_id=None,
            conversation_id=conversation_id,
            history=[dict(item) for item in history],
            stream=stream_output,
        )

        final_text = ""
        usage: dict[str, Any] | None = None
        streamed_output = False
        banner_emitted = False
        async for frame in raw_stream:
            event = _parse_sse_frame(frame)
            if event is None:
                continue

            event_type = str(event.get("type") or "").strip()
            if event_type == "assistant_delta":
                text = str(event.get("text") or "")
                if stream_output and text:
                    if previous_results and not banner_emitted:
                        await stream.emit(
                            "assistant_delta",
                            {
                                "agent_id": SMART_AGENT_ID,
                                "text": "\n\n[{name}]\n".format(
                                    name=str(candidate.get("name") or resolved_agent_id)
                                ),
                            },
                        )
                        banner_emitted = True
                    await stream.emit(
                        "assistant_delta",
                        {
                            "agent_id": SMART_AGENT_ID,
                            "text": text,
                        },
                    )
                    streamed_output = True
                continue

            if event_type == "assistant_message":
                final_text = str(event.get("text") or final_text).strip()
                payload_usage = event.get("usage")
                if isinstance(payload_usage, dict):
                    usage = payload_usage
                continue

            if event_type in {"run_started", "run_completed"}:
                continue

            await self._relay_subagent_event(
                stream=stream,
                event_type=event_type,
                event=event,
                step_index=step_index,
                routed_agent_id=resolved_agent_id,
                routed_agent_name=str(candidate.get("name") or resolved_agent_id),
            )
            if event_type == "error" and not final_text.strip():
                final_text = str(event.get("message") or "").strip()

        return RoutedAgentResult(
            agent_id=resolved_agent_id,
            agent_name=str(candidate.get("name") or resolved_agent_id),
            mode=resolved_mode,
            goal=step.goal.strip(),
            rationale=step.rationale.strip(),
            text=final_text.strip(),
            usage=usage,
            streamed_output=streamed_output,
        )

    async def _relay_subagent_event(
        self,
        *,
        stream: stream_progress.EventStream,
        event_type: str,
        event: Mapping[str, Any],
        step_index: int,
        routed_agent_id: str,
        routed_agent_name: str,
    ) -> None:
        if (
            event_type != "thinking_step"
            and event_type not in ROUTING_DEBUG_EVENT_TYPES
        ):
            if event_type == "error":
                await stream.emit(
                    "thinking_step",
                    {
                        "agent_id": SMART_AGENT_ID,
                        "source_agent_id": routed_agent_id,
                        "source_agent_name": routed_agent_name,
                        "channel": "thinking",
                        "step_id": "smart.{step}.error".format(step=step_index),
                        "label": "{agent}: encountered an issue".format(
                            agent=routed_agent_name
                        ),
                        "detail": str(
                            event.get("message") or "This delegated agent hit an error."
                        ),
                        "state": "error",
                        "message": _prefix_agent_message(
                            routed_agent_name,
                            str(
                                event.get("message")
                                or "This delegated agent hit an error."
                            ),
                        ),
                    },
                )
            return

        payload = dict(event)
        payload["agent_id"] = SMART_AGENT_ID
        payload["source_agent_id"] = routed_agent_id
        payload["source_agent_name"] = routed_agent_name
        payload.setdefault(
            "channel", "thinking" if event_type == "thinking_step" else "debug"
        )

        if event_type == "thinking_step":
            payload["step_id"] = "smart.{step}.{detail}".format(
                step=step_index,
                detail=str(event.get("step_id") or "work").strip() or "work",
            )
            payload["label"] = "{agent}: {label}".format(
                agent=routed_agent_name,
                label=str(event.get("label") or "Working through the request"),
            )
            payload["message"] = _prefix_agent_message(
                routed_agent_name,
                str(
                    event.get("message")
                    or event.get("detail")
                    or event.get("label")
                    or "Working through the request."
                ),
            )
        else:
            payload["display_text"] = _prefix_agent_message(
                routed_agent_name,
                str(
                    event.get("display_text")
                    or event.get("message")
                    or event.get("detail")
                    or event.get("reason")
                    or event_type
                ),
            )

        await stream.emit(event_type, payload)

    def _build_delegated_message(
        self,
        *,
        user_message: str,
        step_index: int,
        step: RoutedAgentStep,
        previous_results: Sequence[RoutedAgentResult],
    ) -> str:
        lines = [
            "You are the selected agent for the next step.",
            "Original user request:",
            user_message.strip(),
            "",
            "Current coordination step: {index}".format(index=step_index),
        ]
        if step.goal.strip():
            lines.extend(["Your goal for this step:", step.goal.strip()])
        if step.rationale.strip():
            lines.extend(["Why you were chosen:", step.rationale.strip()])
        if previous_results:
            lines.extend(["", "Previous delegated outputs:"])
            for index, result in enumerate(previous_results, start=1):
                lines.append(
                    "{index}. {name} ({agent_id}, {mode})".format(
                        index=index,
                        name=result.agent_name,
                        agent_id=result.agent_id,
                        mode=result.mode,
                    )
                )
                lines.append(result.text.strip() or "[no response]")
                lines.append("")
        lines.append(
            "Respond only with your own contribution. Do not invent other agents or describe the routing system."
        )
        return "\n".join(line for line in lines if line is not None).strip()

    def _compose_fallback_answer(self, results: Sequence[RoutedAgentResult]) -> str:
        usable = [result for result in results if result.text.strip()]
        if not usable:
            return ""
        if len(usable) == 1:
            return usable[0].text.strip()

        lines = [
            "Agent route: {route}".format(
                route=" -> ".join(result.agent_name for result in usable)
            ),
            "",
        ]
        for result in usable:
            lines.append("### {name}".format(name=result.agent_name))
            lines.append(result.text.strip())
            lines.append("")
        return "\n".join(lines).strip()

    def _candidate_lookup(
        self,
        agent_id: str,
        candidates: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        normalized_agent_id = str(agent_id or "").strip()
        for candidate in candidates:
            if str(candidate.get("id") or "").strip() == normalized_agent_id:
                return candidate
        raise KeyError("Unknown routed agent id: {agent_id}".format(agent_id=agent_id))

    def _routing_candidates(
        self,
        team_agent_ids: Sequence[str],
    ) -> list[dict[str, Any]]:
        candidates = self.platform.routing_candidates(refresh=True)
        selected_ids = {
            str(agent_id or "").strip()
            for agent_id in team_agent_ids
            if str(agent_id or "").strip()
        }
        if not selected_ids:
            return candidates

        return [
            dict(candidate)
            for candidate in candidates
            if str(candidate.get("id") or "").strip() in selected_ids
        ]


def _decision_instruction() -> str:
    return "\n".join(
        [
            "You coordinate a fixed catalog of agents.",
            "Return strict JSON only.",
            'Schema: {"action":"delegate|finalize","rationale":"...","agent_id":"...","mode":"direct|orchestrated","goal":"...","answer":"..."}',
            "Rules:",
            "- Use only the provided agent ids and modes from the catalog.",
            "- At each turn either delegate to exactly one agent or finalize the answer.",
            "- Finalize when the catalog facts and prior delegated outputs are enough.",
            "- Never invent capabilities, tools, or facts beyond the provided catalog and delegated outputs.",
            "- Keep rationale and goal short.",
            "- When action=finalize, put the complete user-facing answer in answer.",
            "- When action=delegate, answer must be blank.",
            "- Return JSON only and nothing else.",
        ]
    )


def _decision_message(
    *,
    message: str,
    history: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    results: Sequence[RoutedAgentResult],
) -> str:
    lines = [
        "User request:",
        str(message or "").strip(),
        "",
        "Recent conversation history:",
    ]

    recent_history = []
    for item in history[-6:]:
        role = str(item.get("role") or "").strip()
        text = _compact_text(item.get("text") or "", limit=280)
        if role and text:
            recent_history.append("{role}: {text}".format(role=role, text=text))
    lines.append("\n".join(recent_history) if recent_history else "[none]")
    lines.extend(
        [
            "",
            "Available agent catalog:",
            json.dumps(_serialize_candidates(candidates), ensure_ascii=True, indent=2),
            "",
            "Delegated outputs collected so far:",
            json.dumps(_serialize_results(results), ensure_ascii=True, indent=2),
        ]
    )
    return "\n".join(lines).strip()


def _serialize_candidates(
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for candidate in candidates:
        serialized.append(
            {
                "id": candidate.get("id"),
                "name": candidate.get("name"),
                "description": candidate.get("description"),
                "default_mode": candidate.get("default_mode"),
                "runtime_modes": candidate.get("runtime_modes"),
                "tools": candidate.get("tools"),
                "behavior": candidate.get("behavior"),
                "knowledge": candidate.get("knowledge"),
            }
        )
    return serialized


def _serialize_results(
    results: Sequence[RoutedAgentResult],
) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for result in results:
        serialized.append(
            {
                "agent_id": result.agent_id,
                "agent_name": result.agent_name,
                "mode": result.mode,
                "goal": result.goal,
                "rationale": result.rationale,
                "text": _compact_text(result.text, limit=1200),
            }
        )
    return serialized


def _parse_sse_frame(frame: str) -> dict[str, Any] | None:
    event_type = "message"
    data_lines: list[str] = []
    for raw_line in str(frame or "").splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())

    if not data_lines:
        return None

    payload: dict[str, Any]
    try:
        loaded = json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        payload = {
            "message": "Failed to parse stream payload.",
            "raw": "\n".join(data_lines),
        }
    else:
        payload = loaded if isinstance(loaded, dict) else {"payload": loaded}

    payload.setdefault("type", event_type)
    return payload


def _extract_json_payload(text: str) -> dict[str, Any]:
    normalized_text = str(text or "").strip()
    if not normalized_text:
        raise ValueError("Planner returned an empty payload.")
    try:
        payload = json.loads(normalized_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", normalized_text, re.DOTALL)
        if not match:
            raise ValueError("Planner response did not contain valid JSON.")
        payload = json.loads(match.group(0))

    if not isinstance(payload, dict):
        raise ValueError("Planner JSON must be an object.")
    return payload


def _compact_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return "{prefix}...".format(prefix=text[: limit - 3].rstrip())


def _prefix_agent_message(agent_name: str, message: str) -> str:
    cleaned = " ".join(str(message or "").split()).strip()
    if not cleaned:
        return agent_name
    return "{agent}: {message}".format(agent=agent_name, message=cleaned)


def _merge_usage_payloads(
    usages: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    merged_calls: list[Any] = []
    summary = {
        "call_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "tool_use_prompt_tokens": 0,
        "thoughts_tokens": 0,
        "cached_content_tokens": 0,
        "total_tokens": 0,
    }
    saw_usage = False

    for usage in usages:
        if not isinstance(usage, Mapping) or not usage:
            continue
        saw_usage = True
        for key in summary:
            summary[key] += _as_int(usage.get(key))
        calls = usage.get("calls")
        if isinstance(calls, list):
            merged_calls.extend(calls)

    if not saw_usage:
        return None

    summary["calls"] = merged_calls
    return summary


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
