from __future__ import annotations

import asyncio
import contextlib
import contextvars
import os
from typing import Any, Dict, Optional
from uuid import uuid4

from google.adk.sessions import InMemorySessionService
from google.genai import types

import core.contracts.agent as contracts_agent
import core.contracts.execution as contracts_execution
import core.contracts.hooks as contracts_hooks
import core.contracts.tools as contracts_tools
import core.guardrails as guardrails_module
import core.registry as registry
import core.execution.shared.adk as runtime_adk
import core.execution.direct.prompts as runtime_prompts
import core.execution.shared.tooling as runtime_tooling
import core.execution.shared.types as runtime_types
import core.skills.context as skills_context
import core.skills.resolver as skills_resolver
import core.skills.store as skills_store
import core.stream.messages as stream_messages
import core.stream.progress as stream_progress


DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_MODEL_TIMEOUT_SECONDS = 60.0


class DirectAgentRuntime:
    def __init__(self, record: runtime_types.AgentRecord) -> None:
        self.record = record
        self.definition = registry.Register.get(contracts_agent.Agent, record.agent_name)
        self.execution: contracts_execution.ExecutionConfig = self.definition.execution
        self.hooks: contracts_hooks.AgentHooks = self.definition.hooks
        self.model_name, self._model_source = self._resolve_model_name()
        self.model_timeout_seconds = self._resolve_model_timeout_seconds()
        self._resolved_tools = contracts_tools.ensure_tools(self.definition.tools)
        self._tool_definitions: Dict[str, contracts_tools.ToolDefinition] = {
            tool.name: tool
            for tool in self._resolved_tools
        }
        self._tool_descriptions: Dict[str, str] = {
            tool.name: (tool.description or "")
            for tool in self._resolved_tools
        }
        self._resolved_skills: contextvars.ContextVar[skills_resolver.ResolvedSkillContext] = contextvars.ContextVar(
            "resolved_skills_{agent_id}".format(agent_id=record.agent_id.replace(".", "_")),
            default=skills_resolver.ResolvedSkillContext(),
        )
        self._tool_guardrails: contextvars.ContextVar[Optional[guardrails_module.ToolLoopGuardrails]] = contextvars.ContextVar(
            "tool_guardrails_{agent_id}".format(agent_id=record.agent_id.replace(".", "_")),
            default=None,
        )
        self.skill_store = self._load_skill_store()
        self.skill_resolver = skills_resolver.SkillResolver(self.skill_store)
        self._session_service = InMemorySessionService()
        self._session_keys = set()
        self._tool_callables = self._build_tool_callables()
        self.agent = self._build_adk_agent()
        self.runner = self._create_runner()

    def _build_tool_callables(self) -> Dict[str, Any]:
        return {
            tool.name: runtime_tooling.build_guarded_tool_callable(
                tool,
                agent_id=self.record.agent_id,
                tool_guardrails=self._tool_guardrails,
            )
            for tool in self._resolved_tools
        }

    def _resolve_model_name(self) -> tuple[str, str]:
        explicit_model = (self.definition.model or "").strip()
        if explicit_model:
            return explicit_model, "agent"

        env_model = (os.getenv("MODEL_NAME") or "").strip()
        if env_model:
            return env_model, "env"

        return DEFAULT_MODEL, "default"

    def _resolve_model_timeout_seconds(self) -> float:
        raw_value = os.getenv("MODEL_RESPONSE_TIMEOUT_SECONDS", str(DEFAULT_MODEL_TIMEOUT_SECONDS))
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return DEFAULT_MODEL_TIMEOUT_SECONDS
        return value if value > 0 else DEFAULT_MODEL_TIMEOUT_SECONDS

    def _load_skill_store(self) -> skills_store.SkillStore:
        return skills_store.SkillStore(self.record.project_root / "skills")

    def _build_adk_agent(self):
        instruction = runtime_prompts.build_agent_instruction(
            definition=self.definition,
            tool_definitions=tuple(self._tool_definitions.values()),
            execution=self.execution,
            additional_guidance=self.hooks.build_prompt_guidance(phase="direct", state={}),
        )
        return runtime_adk.create_llm_agent(
            agent_id=self.record.agent_id,
            model_name=self.model_name,
            instruction=instruction,
            tool_callables=list(self._tool_callables.values()),
            before_model_callback=self._before_model_callback,
        )

    def _create_runner(self):
        return runtime_adk.create_runner(
            agent=self.agent,
            session_service=self._session_service,
        )

    def _before_model_callback(self, callback_context: Any, llm_request: Any) -> Any:
        runtime_prompts.apply_runtime_context(llm_request, self._resolved_skills.get())
        return None

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
        message = "Timed out waiting for {model} after {seconds} seconds.".format(
            model=active_model,
            seconds=seconds,
        )
        if self._model_source == "env" and self.model_name != DEFAULT_MODEL:
            return (
                "{message} The current .env sets MODEL_NAME to {configured}. "
                "Remove that setting to fall back to {default_model}, or replace it "
                "with a model that responds for your account. If the default model "
                "also times out, check outbound network access and API key permissions."
            ).format(
                message=message,
                configured=self.model_name,
                default_model=DEFAULT_MODEL,
            )
        return (
            "{message} Check outbound network access, model availability, and API "
            "key permissions if this keeps happening."
        ).format(message=message)

    async def _emit_model_waiting_updates(
        self,
        stream: stream_progress.EventStream,
        model_name: Optional[str] = None,
    ) -> None:
        try:
            while True:
                await asyncio.sleep(5)
                await stream_progress.emit_debug_event(
                    "model_waiting",
                    agent_id=self.record.agent_id,
                    model=model_name or self.model_name,
                    message=self._model_waiting_message(model_name),
                )
        except asyncio.CancelledError:
            return

    async def _emit_terminal_error(
        self,
        stream: stream_progress.EventStream,
        *,
        session_id: str,
        message: str,
        error: str,
        assistant_text: str = "",
    ) -> None:
        await stream_progress.emit_thinking_step(
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
        stream = stream_progress.EventStream()
        asyncio.create_task(self._run_chat(stream, message, user_id, active_session_id))
        return active_session_id, stream.sse_messages()

    async def _run_chat(
        self,
        stream: stream_progress.EventStream,
        message: str,
        user_id: str,
        session_id: str,
    ) -> None:
        stream_token = stream_progress.bind_progress_stream(stream)
        resolved_token: Optional[contextvars.Token] = None
        tool_guardrails_token: Optional[contextvars.Token] = None
        skill_store_token: Optional[contextvars.Token] = None
        assistant_buffer = ""
        hook_state = self.hooks.create_turn_state(
            agent_id=self.record.agent_id,
            user_id=user_id,
            session_id=session_id,
            message=message,
        )

        try:
            skill_store_token = skills_context.bind_skill_store(self.skill_store)
            tool_guardrails_token = self._tool_guardrails.set(guardrails_module.ToolLoopGuardrails(self.execution))
            await self.ensure_session(user_id=user_id, session_id=session_id)
            resolved_context = await self._prepare_turn(
                stream=stream,
                message=message,
                user_id=user_id,
                session_id=session_id,
            )
            resolved_token = self._resolved_skills.set(resolved_context)

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

            assistant_buffer = await self._execute_model_turn(
                stream=stream,
                message=message,
                user_id=user_id,
                session_id=session_id,
                resolved_context=resolved_context,
                hook_state=hook_state,
            )
            await stream.emit(
                "run_completed",
                {
                    "agent_id": self.record.agent_id,
                    "session_id": session_id,
                    "message": stream_messages.build_run_completed_message(self.definition.name),
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
            message_text = stream_messages.build_error_message(str(exc))
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
            if tool_guardrails_token is not None:
                self._tool_guardrails.reset(tool_guardrails_token)
            if skill_store_token is not None:
                skills_context.reset_skill_store(skill_store_token)
            stream_progress.reset_progress_stream(stream_token)
            await stream.close()

    async def _prepare_turn(
        self,
        *,
        stream: stream_progress.EventStream,
        message: str,
        user_id: str,
        session_id: str,
    ) -> skills_resolver.ResolvedSkillContext:
        await stream.emit(
            "run_started",
            {
                "agent_id": self.record.agent_id,
                "session_id": session_id,
                "user_id": user_id,
                "message": stream_messages.build_run_started_message(self.definition.name),
            },
        )
        await stream_progress.emit_thinking_step(
            step_id="understand_request",
            label="Understanding the question",
            detail="Working out the most reliable way to answer it.",
            state="running",
            agent_id=self.record.agent_id,
        )
        resolved_context = await asyncio.to_thread(self._resolve_skills, message, user_id)
        await stream_progress.emit_debug_event(
            "skill_context_selected",
            agent_id=self.record.agent_id,
            skills=skills_resolver.serialize_resolved_skills(resolved_context),
            chunks=[
                {
                    "skill_id": chunk.skill_id,
                    "source": chunk.source,
                    "heading": chunk.heading,
                    "preview": chunk.text[:220],
                }
                for chunk in resolved_context.chunks
            ],
            message=skills_resolver.describe_resolved_skill_context(resolved_context),
        )
        skill_label, skill_detail, skill_state = runtime_prompts.skill_context_thinking(resolved_context)
        await stream_progress.emit_thinking_step(
            step_id="guidance",
            label=skill_label,
            detail=skill_detail,
            state=skill_state,
            agent_id=self.record.agent_id,
        )
        await stream_progress.emit_thinking_step(
            step_id="planning",
            label="Planning the approach",
            detail=runtime_prompts.planning_thinking_detail(resolved_context),
            state="done",
            agent_id=self.record.agent_id,
        )
        return resolved_context

    async def _execute_model_turn(
        self,
        *,
        stream: stream_progress.EventStream,
        message: str,
        user_id: str,
        session_id: str,
        resolved_context: skills_resolver.ResolvedSkillContext,
        hook_state: contracts_hooks.HookState,
    ) -> str:
        await stream.emit(
            "model_started",
            {
                "agent_id": self.record.agent_id,
                "session_id": session_id,
                "model": self.model_name,
                "message": self._model_started_message(),
            },
        )
        await stream_progress.emit_thinking_step(
            step_id="understand_request",
            label="Planning the answer",
            detail="Deciding whether the answer needs only guidance, one tool, or a multi-step tool sequence.",
            state="done",
            agent_id=self.record.agent_id,
        )
        await stream_progress.emit_thinking_step(
            step_id="answer",
            label="Working through the answer",
            detail="Pulling together the information needed before writing the reply.",
            state="running",
            agent_id=self.record.agent_id,
        )

        assistant_buffer = ""
        heartbeat_task = asyncio.create_task(
            self._emit_model_waiting_updates(stream, self.model_name)
        )
        try:
            user_content = types.Content(role="user", parts=[types.Part(text=message)])
            async with asyncio.timeout(self.model_timeout_seconds):
                async for event in runtime_adk.stream_runner_events(
                    runner=self.runner,
                    user_id=user_id,
                    session_id=session_id,
                    new_message=user_content,
                ):
                    assistant_buffer = await self._handle_runner_event(
                        stream=stream,
                        event=event,
                        message=message,
                        resolved_context=resolved_context,
                        assistant_buffer=assistant_buffer,
                        hook_state=hook_state,
                    )
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

        return assistant_buffer

    async def _handle_runner_event(
        self,
        *,
        stream: stream_progress.EventStream,
        event: Any,
        message: str,
        resolved_context: skills_resolver.ResolvedSkillContext,
        assistant_buffer: str,
        hook_state: contracts_hooks.HookState,
    ) -> str:
        text = runtime_adk.extract_text(event)
        function_calls = list(event.get_function_calls() or [])
        function_responses = list(event.get_function_responses() or [])

        await self._emit_tool_call_events(
            function_calls=function_calls,
            message=message,
            resolved_context=resolved_context,
            model_hint=text,
        )
        await self._emit_tool_response_events(
            function_responses=function_responses,
            hook_state=hook_state,
        )

        if getattr(event, "partial", False) and text:
            assistant_buffer += text
            await stream_progress.emit_thinking_step(
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
            return assistant_buffer

        if event.is_final_response() and (text or assistant_buffer):
            final_text = "{buffer}{tail}".format(buffer=assistant_buffer, tail=text).strip()
            final_text = self.hooks.finalize_response(text=final_text, state=hook_state)
            await stream_progress.emit_thinking_step(
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
            return ""

        if not function_calls and not function_responses:
            await stream_progress.emit_debug_event(
                "agent_event",
                agent_id=self.record.agent_id,
                author=getattr(event, "author", None),
                event_id=getattr(event, "id", None),
            )
        return assistant_buffer

    async def _emit_tool_call_events(
        self,
        *,
        function_calls: list[Any],
        message: str,
        resolved_context: skills_resolver.ResolvedSkillContext,
        model_hint: str,
    ) -> None:
        for call in function_calls:
            selection_reason = runtime_prompts.build_tool_selection_reason(
                tool_name=call.name,
                tool_args=call.args or {},
                user_message=message,
                selected_chunks=list(resolved_context.chunks),
                model_hint=model_hint,
                tool_descriptions=self._tool_descriptions,
            )
            await stream_progress.emit_debug_event(
                "tool_selection_reason",
                agent_id=self.record.agent_id,
                tool_name=call.name,
                reason=selection_reason,
                message=stream_messages.build_tool_selection_message(call.name, selection_reason),
            )
            await stream_progress.emit_debug_event(
                "tool_started",
                agent_id=self.record.agent_id,
                tool_name=call.name,
                args=call.args,
                message=stream_messages.build_tool_started_message(call.name, call.args or {}),
            )

    async def _emit_tool_response_events(
        self,
        *,
        function_responses: list[Any],
        hook_state: Optional[contracts_hooks.HookState] = None,
    ) -> None:
        for response in function_responses:
            if hook_state is not None:
                self.hooks.on_tool_response(
                    state=hook_state,
                    tool_name=response.name,
                    payload=response.response,
                )
            await stream_progress.emit_debug_event(
                "tool_completed",
                agent_id=self.record.agent_id,
                tool_name=response.name,
                response=response.response,
                message=stream_messages.build_tool_completed_message(
                    response.name,
                    response.response,
                ),
            )

    def _resolve_skills(self, query: str, user_id: str) -> skills_resolver.ResolvedSkillContext:
        return self.skill_resolver.resolve(
            query=query,
            user_id=user_id,
            skill_scopes=self.definition.skill_scopes,
            always_on_skill_ids=self.definition.always_on_skills,
        )
