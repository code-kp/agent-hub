from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from google.genai import types

try:
    from google.adk.agents import LlmAgent
except ImportError:  # pragma: no cover
    from google.adk.agent import Agent as LlmAgent  # type: ignore

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from core.stream.messages import (
    build_error_message,
    build_run_completed_message,
    build_run_started_message,
    build_tool_completed_message,
    build_tool_selection_message,
    build_tool_started_message,
)
from core.contracts.agent import Agent
from core.contracts.tools import ToolDefinition
from core.stream.progress import (
    EventStream,
    bind_progress_stream,
    emit_debug_event,
    emit_thinking_step,
    reset_progress_stream,
)
from core.registry import Register
from core.skills.resolver import (
    ResolvedSkillContext,
    SkillResolver,
    describe_resolved_skill_context,
    serialize_resolved_skills,
)
from core.skills.store import SkillChunk, SkillStore
from core.policies.tool_policy import (
    IntentAnalysis,
    PlannedToolCall,
    ToolExecutionPlan,
    format_intent_for_thinking,
    plan_tool_execution,
)


DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_MODEL_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class AgentRecord:
    agent_id: str
    module_name: str
    agent_name: str
    project_name: str
    project_root: Path
    fingerprint: str


@dataclass(frozen=True)
class PreflightToolResult:
    tool_name: str
    tool_args: Dict[str, Any]
    rationale: str
    response: Any


class AgentRuntime:
    def __init__(self, record: AgentRecord) -> None:
        self.record = record
        self.definition = Register.get(Agent, record.agent_name)
        self.model_name, self._model_source = self._resolve_model_name()
        self.model_timeout_seconds = self._resolve_model_timeout_seconds()
        self._tool_definitions: Dict[str, ToolDefinition] = {
            tool.name: tool
            for tool in self.definition.tools
        }
        self._tool_callables: Dict[str, Any] = {
            tool.name: tool.build_callable()
            for tool in self.definition.tools
        }
        self._tool_descriptions: Dict[str, str] = {
            tool.name: (tool.description or "")
            for tool in self.definition.tools
        }
        self._resolved_skills: contextvars.ContextVar[ResolvedSkillContext] = contextvars.ContextVar(
            "resolved_skills_{agent_id}".format(agent_id=record.agent_id.replace(".", "_")),
            default=ResolvedSkillContext(),
        )
        self._preflight_results: contextvars.ContextVar[tuple[PreflightToolResult, ...]] = contextvars.ContextVar(
            "preflight_results_{agent_id}".format(agent_id=record.agent_id.replace(".", "_")),
            default=(),
        )
        self.skill_store = self._load_skill_store()
        self.skill_resolver = SkillResolver(self.skill_store)
        self._session_service = InMemorySessionService()
        self._session_keys = set()
        self.agent = self._build_adk_agent()
        self.runner = self._create_runner()

    def _resolve_model_name(self) -> tuple[str, str]:
        explicit_model = (self.definition.model or "").strip()
        if explicit_model:
            return explicit_model, "agent"

        env_model = (os.getenv("MODEL_NAME") or "").strip()
        if env_model:
            return env_model, "env"

        return DEFAULT_MODEL, "default"

    def _create_runner(self) -> Runner:
        return Runner(
            app_name="agent_hub",
            agent=self.agent,
            session_service=self._session_service,
        )

    def _load_skill_store(self) -> SkillStore:
        return SkillStore(self.record.project_root / "skills")

    def _build_adk_agent(self) -> LlmAgent:
        instruction = "\n\n".join(
            part
            for part in [
                "Agent name: {name}".format(name=self.definition.name),
                "Agent description: {description}".format(description=self.definition.description),
                self.definition.system_prompt.strip(),
                self._build_tool_policy_instruction(),
                "Use tools when they improve accuracy and keep responses concise.",
            ]
            if part
        )
        return LlmAgent(
            name=self.record.agent_id.replace(".", "_"),
            model=self.model_name,
            instruction=instruction,
            tools=list(self._tool_callables.values()),
            before_model_callback=self._before_model_callback,
        )

    def _resolve_model_timeout_seconds(self) -> float:
        raw_value = os.getenv("MODEL_RESPONSE_TIMEOUT_SECONDS", str(DEFAULT_MODEL_TIMEOUT_SECONDS))
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return DEFAULT_MODEL_TIMEOUT_SECONDS
        return value if value > 0 else DEFAULT_MODEL_TIMEOUT_SECONDS

    def _missing_credentials_message(self) -> str:
        return (
            "Google API key is not configured. Set GOOGLE_API_KEY in the project .env "
            "before chatting with agents."
        )

    def _model_started_message(self, model_name: Optional[str] = None) -> str:
        active_model = model_name or self.model_name
        return "Sending the request to {model}.".format(model=active_model)

    def _model_waiting_message(self, model_name: Optional[str] = None) -> str:
        active_model = model_name or self.model_name
        return "Still waiting for a response from {model}.".format(model=active_model)

    def _model_timeout_message(self, model_name: Optional[str] = None) -> str:
        active_model = model_name or self.model_name
        seconds = int(self.model_timeout_seconds)
        message = (
            "Timed out waiting for {model} after {seconds} seconds."
            .format(model=active_model, seconds=seconds)
        )
        if (
            getattr(self, "_model_source", "default") == "env"
            and self.model_name != DEFAULT_MODEL
        ):
            message = (
                "{message} The current .env sets MODEL_NAME to {configured}. "
                "Remove that setting to fall back to {default_model}, or replace it "
                "with a model that responds for your account. If the default model "
                "also times out, check outbound network access and API key permissions."
            ).format(
                message=message,
                configured=self.model_name,
                default_model=DEFAULT_MODEL,
            )
        else:
            message = (
                "{message} Check outbound network access, model availability, and API "
                "key permissions if this keeps happening."
            ).format(message=message)
        return message

    async def _emit_model_waiting_updates(
        self,
        stream: EventStream,
        model_name: Optional[str] = None,
    ) -> None:
        try:
            while True:
                await asyncio.sleep(5)
                await emit_debug_event(
                    "model_waiting",
                    agent_id=self.record.agent_id,
                    model=model_name or self.model_name,
                    message=self._model_waiting_message(model_name),
                )
        except asyncio.CancelledError:
            return

    async def _emit_terminal_error(
        self,
        stream: EventStream,
        *,
        session_id: str,
        message: str,
        error: str,
        assistant_text: str = "",
    ) -> None:
        await emit_thinking_step(
            step_id="answer",
            label="Could not complete the answer",
            detail=message,
            state="error",
            agent_id=self.record.agent_id,
        )
        if assistant_text.strip():
            await stream.emit(
                "assistant_message",
                {
                    "agent_id": self.record.agent_id,
                    "text": assistant_text.strip(),
                },
            )
        await stream.emit(
            "error",
            {
                "agent_id": self.record.agent_id,
                "session_id": session_id,
                "message": message,
                "error": error,
            },
        )

    async def _stream_runner_events(
        self,
        *,
        runner: Runner,
        user_id: str,
        session_id: str,
        new_message: types.Content,
    ) -> AsyncIterator[Any]:
        event_queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        context = contextvars.copy_context()

        async def produce() -> None:
            try:
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=new_message,
                ):
                    loop.call_soon_threadsafe(event_queue.put_nowait, ("event", event))
            except Exception as exc:
                loop.call_soon_threadsafe(event_queue.put_nowait, ("error", exc))
            finally:
                loop.call_soon_threadsafe(event_queue.put_nowait, ("done", None))

        def thread_main() -> None:
            context.run(lambda: asyncio.run(produce()))

        thread = threading.Thread(target=thread_main, daemon=True)
        thread.start()

        while True:
            kind, payload = await event_queue.get()
            if kind == "event":
                yield payload
                continue
            if kind == "error":
                raise payload
            break

    def _before_model_callback(self, callback_context: Any, llm_request: Any) -> Any:
        resolved_context = self._resolved_skills.get()
        preflight_results = self._preflight_results.get()

        config = getattr(llm_request, "config", None)
        if config is None:
            return None

        skill_prompt = self._format_skill_context(resolved_context)
        preflight_prompt = self._format_preflight_context(preflight_results)
        prompt_sections = [section for section in [skill_prompt, preflight_prompt] if section]
        if not prompt_sections:
            return None

        system_instruction = config.system_instruction or types.Content(role="system", parts=[])
        if not isinstance(system_instruction, types.Content):
            system_instruction = types.Content(
                role="system",
                parts=[types.Part(text=str(system_instruction))],
            )
        if not system_instruction.parts:
            system_instruction.parts.append(types.Part(text=""))

        marker = "Relevant runtime context for this turn:"
        existing = system_instruction.parts[0].text or ""
        if marker not in existing:
            runtime_context = "\n\n".join(
                ["Relevant runtime context for this turn:", *prompt_sections]
            )
            system_instruction.parts[0].text = "{existing}\n\n{runtime_context}".format(
                existing=existing.strip(),
                runtime_context=runtime_context,
            ).strip()
            config.system_instruction = system_instruction
        return None

    def _format_skill_context(self, context: ResolvedSkillContext) -> str:
        if context.is_empty:
            return ""
        lines = [
            "Skill context:",
            "Use these summaries and excerpts only when they materially help answer the user.",
        ]
        if context.always_on_skills:
            lines.append("Always-on skills:")
            for skill in context.always_on_skills:
                lines.append(
                    "- [{skill_id}] ({skill_type}) {title}: {summary}".format(
                        skill_id=skill.id,
                        skill_type=skill.skill_type,
                        title=skill.title,
                        summary=skill.summary,
                    )
                )
        if context.selected_skills:
            lines.append("Retrieved skills:")
            for skill in context.selected_skills:
                lines.append(
                    "- [{skill_id}] ({skill_type}) {title}: {summary}".format(
                        skill_id=skill.id,
                        skill_type=skill.skill_type,
                        title=skill.title,
                        summary=skill.summary,
                    )
                )
        if context.chunks:
            lines.append("Detailed excerpts:")
            for chunk in context.chunks:
                lines.append("[{label}]".format(label=chunk.label))
                lines.append(chunk.text)
        return "\n\n".join(lines)

    def _format_preflight_context(self, results: tuple[PreflightToolResult, ...]) -> str:
        if not results:
            return ""
        lines = [
            "Preflight tool context:",
            "Use these required checks before deciding whether additional tool calls are still needed.",
        ]
        for item in results:
            lines.append(
                "- [{tool_name}] {rationale}".format(
                    tool_name=item.tool_name,
                    rationale=item.rationale,
                )
            )
            lines.append(self._summarize_tool_response(item.tool_name, item.response))
        return "\n\n".join(lines)

    async def ensure_session(self, user_id: str, session_id: str) -> None:
        key = (user_id, session_id)
        if key in self._session_keys:
            return
        created = self._session_service.create_session(
            app_name="agent_hub",
            user_id=user_id,
            session_id=session_id,
        )
        if asyncio.iscoroutine(created):
            await created
        self._session_keys.add(key)

    async def stream_chat(
        self,
        message: str,
        user_id: str,
        session_id: Optional[str] = None,
    ):
        active_session_id = session_id or str(uuid4())
        stream = EventStream()
        asyncio.create_task(self._run_chat(stream, message, user_id, active_session_id))
        return active_session_id, stream.sse_messages()

    async def _run_chat(
        self,
        stream: EventStream,
        message: str,
        user_id: str,
        session_id: str,
    ) -> None:
        stream_token = bind_progress_stream(stream)
        assistant_buffer = ""
        resolved_token: Optional[contextvars.Token] = None
        preflight_token: Optional[contextvars.Token] = None
        resolved_context = ResolvedSkillContext()
        preflight_results: tuple[PreflightToolResult, ...] = ()

        try:
            await self.ensure_session(user_id=user_id, session_id=session_id)
            await stream.emit(
                "run_started",
                {
                    "agent_id": self.record.agent_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "message": build_run_started_message(self.definition.name),
                },
            )
            await emit_thinking_step(
                step_id="understand_request",
                label="Understanding the question",
                detail="Working out the most reliable way to answer it.",
                state="running",
                agent_id=self.record.agent_id,
            )
            resolved_context = await asyncio.to_thread(self._resolve_skills, message, user_id)
            resolved_token = self._resolved_skills.set(resolved_context)
            await emit_debug_event(
                "skill_context_selected",
                agent_id=self.record.agent_id,
                skills=serialize_resolved_skills(resolved_context),
                chunks=[
                    {
                        "skill_id": chunk.skill_id,
                        "source": chunk.source,
                        "heading": chunk.heading,
                        "preview": chunk.text[:220],
                    }
                    for chunk in resolved_context.chunks
                ],
                message=describe_resolved_skill_context(resolved_context),
            )
            skill_label, skill_detail, skill_state = self._skill_context_thinking(resolved_context)
            await emit_thinking_step(
                step_id="guidance",
                label=skill_label,
                detail=skill_detail,
                state=skill_state,
                agent_id=self.record.agent_id,
            )
            tool_plan = self._plan_tool_execution(message, resolved_context)
            await emit_debug_event(
                "tool_plan_created",
                agent_id=self.record.agent_id,
                plan={
                    "intent": {
                        "is_temporal": tool_plan.intent.is_temporal,
                        "asks_for_exact_time": tool_plan.intent.asks_for_exact_time,
                        "needs_public_web": tool_plan.intent.needs_public_web,
                        "should_anchor_to_current_time": tool_plan.intent.should_anchor_to_current_time,
                        "reasons": list(tool_plan.intent.reasons),
                    },
                    "preflight_calls": [
                        {
                            "tool_name": item.tool_name,
                            "tool_args": item.tool_args,
                            "rationale": item.rationale,
                        }
                        for item in tool_plan.preflight_calls
                    ],
                },
            )
            await emit_thinking_step(
                step_id="tool_policy",
                label="Planning tool usage",
                detail=format_intent_for_thinking(tool_plan.intent),
                state="done",
                agent_id=self.record.agent_id,
            )
            if tool_plan.preflight_calls:
                await emit_thinking_step(
                    step_id="required_checks",
                    label="Running required checks",
                    detail=self._preflight_thinking_detail(tool_plan),
                    state="running",
                    agent_id=self.record.agent_id,
                )
                preflight_results = tuple(
                    await self._run_preflight_tools(
                        message=message,
                        selected_chunks=list(resolved_context.chunks),
                        planned_calls=tool_plan.preflight_calls,
                    )
                )
                await emit_thinking_step(
                    step_id="required_checks",
                    label="Required checks completed",
                    detail=self._preflight_completed_detail(preflight_results),
                    state="done",
                    agent_id=self.record.agent_id,
                )
            preflight_token = self._preflight_results.set(preflight_results)

            if not os.getenv("GOOGLE_API_KEY"):
                message_text = self._missing_credentials_message()
                await self._emit_terminal_error(
                    stream,
                    session_id=session_id,
                    message=message_text,
                    error="GOOGLE_API_KEY missing",
                    assistant_text=message_text,
                )
                return

            await stream.emit(
                "model_started",
                {
                    "agent_id": self.record.agent_id,
                    "session_id": session_id,
                    "model": self.model_name,
                    "message": self._model_started_message(),
                },
            )
            await emit_thinking_step(
                step_id="understand_request",
                label="Planning the answer",
                detail="Deciding whether internal guidance, web research, or both are needed.",
                state="done",
                agent_id=self.record.agent_id,
            )
            await emit_thinking_step(
                step_id="answer",
                label="Working through the answer",
                detail="Pulling together the information needed before writing the reply.",
                state="running",
                agent_id=self.record.agent_id,
            )

            heartbeat_task = asyncio.create_task(
                self._emit_model_waiting_updates(stream, self.model_name)
            )
            runner = self.runner

            user_content = types.Content(role="user", parts=[types.Part(text=message)])
            try:
                async with asyncio.timeout(self.model_timeout_seconds):
                    async for event in self._stream_runner_events(
                        runner=runner,
                        user_id=user_id,
                        session_id=session_id,
                        new_message=user_content,
                    ):
                        text = self._extract_text(event)
                        function_calls = list(event.get_function_calls() or [])
                        function_responses = list(event.get_function_responses() or [])

                        for call in function_calls:
                            selection_reason = self._build_tool_selection_reason(
                                tool_name=call.name,
                                tool_args=call.args or {},
                                user_message=message,
                                selected_chunks=list(resolved_context.chunks),
                                model_hint=text,
                            )
                            await emit_debug_event(
                                "tool_selection_reason",
                                agent_id=self.record.agent_id,
                                tool_name=call.name,
                                reason=selection_reason,
                                message=build_tool_selection_message(call.name, selection_reason),
                            )
                            await emit_debug_event(
                                "tool_started",
                                agent_id=self.record.agent_id,
                                tool_name=call.name,
                                args=call.args,
                                message=build_tool_started_message(call.name, call.args or {}),
                            )

                        for response in function_responses:
                            await emit_debug_event(
                                "tool_completed",
                                agent_id=self.record.agent_id,
                                tool_name=response.name,
                                response=response.response,
                                message=build_tool_completed_message(
                                    response.name,
                                    response.response,
                                ),
                            )

                        if getattr(event, "partial", False) and text:
                            assistant_buffer += text
                            await emit_thinking_step(
                                step_id="answer",
                                label="Drafting the answer",
                                detail="Turning the gathered information into a concise reply.",
                                state="running",
                                agent_id=self.record.agent_id,
                            )
                            await stream.emit(
                                "assistant_delta",
                                {
                                    "agent_id": self.record.agent_id,
                                    "text": text,
                                },
                            )
                            continue

                        if event.is_final_response() and (text or assistant_buffer):
                            final_text = "{buffer}{tail}".format(buffer=assistant_buffer, tail=text).strip()
                            assistant_buffer = ""
                            await emit_thinking_step(
                                step_id="answer",
                                label="Answer ready",
                                detail="The key points have been pulled together.",
                                state="done",
                                agent_id=self.record.agent_id,
                            )
                            await stream.emit(
                                "assistant_message",
                                {
                                    "agent_id": self.record.agent_id,
                                    "text": final_text,
                                },
                            )
                        elif not function_calls and not function_responses:
                            await emit_debug_event(
                                "agent_event",
                                agent_id=self.record.agent_id,
                                author=getattr(event, "author", None),
                                event_id=getattr(event, "id", None),
                            )
            finally:
                heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat_task

            await stream.emit(
                "run_completed",
                {
                    "agent_id": self.record.agent_id,
                    "session_id": session_id,
                    "message": build_run_completed_message(self.definition.name),
                },
            )
        except asyncio.TimeoutError:
            self.runner = self._create_runner()
            message_text = self._model_timeout_message()
            await self._emit_terminal_error(
                stream,
                session_id=session_id,
                message=message_text,
                error="model_timeout",
                assistant_text="" if assistant_buffer.strip() else message_text,
            )
        except Exception as exc:
            message_text = build_error_message(str(exc))
            await self._emit_terminal_error(
                stream,
                session_id=session_id,
                message=message_text,
                error=str(exc),
                assistant_text="" if assistant_buffer.strip() else message_text,
            )
        finally:
            if resolved_token is not None:
                self._resolved_skills.reset(resolved_token)
            if preflight_token is not None:
                self._preflight_results.reset(preflight_token)
            reset_progress_stream(stream_token)
            await stream.close()

    def _resolve_skills(self, query: str, user_id: str) -> ResolvedSkillContext:
        return self.skill_resolver.resolve(
            query=query,
            user_id=user_id,
            skill_scopes=self.definition.skill_scopes,
            always_on_skill_ids=self.definition.always_on_skills,
        )

    def _extract_text(self, event: Any) -> str:
        content = getattr(event, "content", None)
        if not content or not getattr(content, "parts", None):
            return ""
        parts = []
        for part in content.parts:
            text = getattr(part, "text", None)
            if text:
                parts.append(text)
        return "".join(parts)

    def _build_tool_selection_reason(
        self,
        *,
        tool_name: str,
        tool_args: Dict[str, Any],
        user_message: str,
        selected_chunks: List[SkillChunk],
        model_hint: str,
    ) -> str:
        reason_parts: List[str] = []

        hint = (model_hint or "").strip()
        if hint:
            normalized_hint = " ".join(hint.split())
            if len(normalized_hint) > 220:
                normalized_hint = "{value}...".format(value=normalized_hint[:217])
            reason_parts.append("Model intent: {hint}".format(hint=normalized_hint))

        description = self._tool_descriptions.get(tool_name, "").strip()
        if description:
            reason_parts.append("Tool capability: {description}".format(description=description))

        arg_keys = sorted(str(key) for key in tool_args.keys())
        if arg_keys:
            reason_parts.append("Inputs provided: {keys}".format(keys=", ".join(arg_keys)))

        user_tokens = {
            token
            for token in re.findall(r"[a-z0-9]{3,}", user_message.lower())
            if len(token) >= 3
        }
        related_chunks = [
            chunk
            for chunk in selected_chunks
            if any(
                token in "{heading} {text}".format(
                    heading=chunk.heading.lower(),
                    text=chunk.text.lower(),
                )
                for token in user_tokens
            )
        ]
        if related_chunks:
            top_chunk = related_chunks[0]
            reason_parts.append(
                "Related skill context: {source} / {heading}".format(
                    source=top_chunk.source,
                    heading=top_chunk.heading,
                )
            )

        if not reason_parts:
            return "Tool was selected by the model for this turn."
        return ". ".join(part.rstrip(".") for part in reason_parts) + "."

    def _build_tool_policy_instruction(self) -> str:
        if not self._tool_definitions:
            return ""

        lines = [
            "Tool usage policy:",
            "First decide whether the request is internal guidance, current public information, a direct time lookup, or a mix.",
            "Reuse any preflight tool outputs already provided before calling the same tool again.",
            "Use one tool when a single check is enough, or chain tools when each step materially improves accuracy.",
            "For time-sensitive public questions, prefer this sequence when available: get_current_utc_time -> search_web -> fetch_web_page.",
            "Tool catalog:",
        ]
        for tool in self._tool_definitions.values():
            lines.extend(self._format_tool_catalog_entry(tool))
        return "\n".join(lines)

    def _format_tool_catalog_entry(self, tool: ToolDefinition) -> List[str]:
        lines = [
            "- {name} [{category}]: {description}".format(
                name=tool.name,
                category=tool.category,
                description=tool.description,
            )
        ]
        if tool.use_when:
            lines.append("  Use when: {items}".format(items="; ".join(tool.use_when)))
        if tool.avoid_when:
            lines.append("  Avoid when: {items}".format(items="; ".join(tool.avoid_when)))
        if tool.returns:
            lines.append("  Returns: {returns}".format(returns=tool.returns))
        if tool.follow_up_tools:
            lines.append(
                "  Often followed by: {tools}".format(
                    tools=", ".join(tool.follow_up_tools)
                )
            )
        if tool.requires_current_data:
            lines.append("  Treat this as a current-data tool.")
        return lines

    def _plan_tool_execution(
        self,
        message: str,
        resolved_context: ResolvedSkillContext,
    ) -> ToolExecutionPlan:
        return plan_tool_execution(
            query=message,
            available_tools=tuple(self._tool_definitions.values()),
            resolved_context=resolved_context,
        )

    async def _run_preflight_tools(
        self,
        *,
        message: str,
        selected_chunks: List[SkillChunk],
        planned_calls: tuple[PlannedToolCall, ...],
    ) -> List[PreflightToolResult]:
        results: List[PreflightToolResult] = []
        for item in planned_calls:
            await emit_debug_event(
                "tool_selection_reason",
                agent_id=self.record.agent_id,
                tool_name=item.tool_name,
                reason=item.rationale,
                message=build_tool_selection_message(item.tool_name, item.rationale),
            )
            await emit_debug_event(
                "tool_started",
                agent_id=self.record.agent_id,
                tool_name=item.tool_name,
                args=item.tool_args,
                message=build_tool_started_message(item.tool_name, item.tool_args),
            )
            callable_tool = self._tool_callables.get(item.tool_name)
            if callable_tool is None:
                continue
            response = await callable_tool(**item.tool_args)
            await emit_debug_event(
                "tool_completed",
                agent_id=self.record.agent_id,
                tool_name=item.tool_name,
                response=response,
                message=build_tool_completed_message(item.tool_name, response),
            )
            results.append(
                PreflightToolResult(
                    tool_name=item.tool_name,
                    tool_args=dict(item.tool_args),
                    rationale=item.rationale,
                    response=response,
                )
            )
        return results

    def _summarize_tool_response(self, tool_name: str, response: Any) -> str:
        if tool_name == "get_current_utc_time" and isinstance(response, dict):
            utc_time = str(response.get("utc_time") or "").strip()
            if utc_time:
                return "Current UTC time: {utc_time}".format(utc_time=utc_time)

        if tool_name == "search_web" and isinstance(response, dict):
            queries_used = list(response.get("queries_used") or [])
            results = list(response.get("results") or [])
            lines = []
            if queries_used:
                lines.append(
                    "Queries used: {queries}".format(
                        queries=", ".join('"{query}"'.format(query=query) for query in queries_used)
                    )
                )
            if results:
                lines.append("Top results:")
                for index, item in enumerate(results[:3], start=1):
                    title = str(item.get("title") or "Untitled").strip()
                    url = str(item.get("url") or "").strip()
                    snippet = " ".join(str(item.get("snippet") or "").split()).strip()
                    preview = snippet[:180] + ("..." if len(snippet) > 180 else "")
                    lines.append(
                        "{index}. {title} ({url}) - {preview}".format(
                            index=index,
                            title=title,
                            url=url,
                            preview=preview or "No snippet provided",
                        )
                    )
            return "\n".join(lines) if lines else "No web results were returned."

        if tool_name == "fetch_web_page" and isinstance(response, dict):
            title = str(response.get("title") or "Untitled").strip()
            url = str(response.get("url") or "").strip()
            content = " ".join(str(response.get("content") or "").split()).strip()
            preview = content[:280] + ("..." if len(content) > 280 else "")
            return "{title} ({url})\n{preview}".format(
                title=title,
                url=url,
                preview=preview or "No readable content was extracted.",
            )

        if isinstance(response, dict):
            return json.dumps(response, default=str)
        return str(response)

    def _preflight_thinking_detail(self, plan: ToolExecutionPlan) -> str:
        labels = [item.tool_name for item in plan.preflight_calls]
        if not labels:
            return "No required checks were planned."
        return "Required tool sequence: {labels}.".format(labels=" -> ".join(labels))

    def _preflight_completed_detail(
        self,
        results: tuple[PreflightToolResult, ...],
    ) -> str:
        if not results:
            return "No required checks were needed."
        return "Completed {count} required check(s): {tools}.".format(
            count=len(results),
            tools=", ".join(item.tool_name for item in results),
        )

    def _skill_context_thinking(self, context: ResolvedSkillContext) -> tuple[str, str, str]:
        if context.is_empty:
            return (
                "Checking relevant guidance",
                "No internal guidance was needed for this question.",
                "done",
            )

        if context.selected_skills:
            return (
                "Checking relevant guidance",
                "Pulled in only the small set of guidance that looks useful for this question.",
                "done",
            )

        if context.always_on_skills:
            return (
                "Applying baseline guidance",
                "Using the always-on instructions that shape how this agent responds.",
                "done",
            )

        return (
            "Checking relevant guidance",
            "Prepared the available guidance for this question.",
            "done",
        )
