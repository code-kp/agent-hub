"""
Tests:
- tests/core/execution/direct/test_runtime.py
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import os
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
from uuid import uuid4

from google.adk.sessions import InMemorySessionService
from google.genai import types

import core.contracts.agent as contracts_agent
import core.contracts.execution as contracts_execution
import core.contracts.hooks as contracts_hooks
import core.contracts.memory as contracts_memory
import core.contracts.models as contracts_models
import core.contracts.tools as contracts_tools
import core.guardrails as guardrails_module
import core.memory as memory_module
import core.registry as registry
import core.execution.shared.adk as runtime_adk
import core.execution.shared.models as runtime_models
import core.execution.direct.prompts as runtime_prompts
import core.execution.shared.request_context as request_context
import core.execution.shared.tooling as runtime_tooling
import core.execution.shared.types as runtime_types
import core.execution.shared.usage as runtime_usage
import core.skills.context as skills_context
import core.retrieval.conversations as retrieval_conversations
import core.retrieval.turns as retrieval_turns
import core.skills.resolver as skills_resolver
import core.skills.store as skills_store
import core.stream.messages as stream_messages
import core.stream.progress as stream_progress


DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_MODEL_TIMEOUT_SECONDS = 60.0
MAX_TRANSIENT_MODEL_RETRIES = 1


class DirectAgentRuntime:
    def __init__(
        self,
        record: runtime_types.AgentRecord,
        *,
        model_name_override: str | None = None,
    ) -> None:
        self.record = record
        self.model_name_override = str(model_name_override or "").strip()
        self.definition = registry.Register.get(
            contracts_agent.Agent, record.agent_name
        )
        self.execution: contracts_execution.ExecutionConfig = self.definition.execution
        self.memory: contracts_memory.MemoryConfig = self.definition.memory
        self.hooks: contracts_hooks.AgentHooks = self.definition.hooks
        self.model_name, self._model_source = self._resolve_model_name(
            self.model_name_override
        )
        self.resolved_model = runtime_models.resolve_model(self.model_name)
        self.model_timeout_seconds = self._resolve_model_timeout_seconds()
        self._resolved_tools = contracts_tools.ensure_tools(self.definition.tools)
        self._tool_definitions: Dict[str, contracts_tools.ToolDefinition] = {
            tool.name: tool for tool in self._resolved_tools
        }
        self._tool_descriptions: Dict[str, str] = {
            tool.name: (tool.description or "") for tool in self._resolved_tools
        }
        self._resolved_skills: contextvars.ContextVar[
            skills_resolver.ResolvedSkillContext
        ] = contextvars.ContextVar(
            "resolved_skills_{agent_id}".format(
                agent_id=record.agent_id.replace(".", "_")
            ),
            default=skills_resolver.ResolvedSkillContext(),
        )
        self._turn_context: contextvars.ContextVar[
            retrieval_turns.TurnContextBundle
        ] = contextvars.ContextVar(
            "turn_context_{agent_id}".format(
                agent_id=record.agent_id.replace(".", "_")
            ),
            default=retrieval_turns.TurnContextBundle(),
        )
        self._tool_guardrails: contextvars.ContextVar[
            Optional[guardrails_module.ToolLoopGuardrails]
        ] = contextvars.ContextVar(
            "tool_guardrails_{agent_id}".format(
                agent_id=record.agent_id.replace(".", "_")
            ),
            default=None,
        )
        self._conversation_history: contextvars.ContextVar[list[dict[str, str]]] = (
            contextvars.ContextVar(
                "conversation_history_{agent_id}".format(
                    agent_id=record.agent_id.replace(".", "_")
                ),
                default=[],
            )
        )
        self._conversation_memory: contextvars.ContextVar[
            memory_module.MemorySnapshot
        ] = contextvars.ContextVar(
            "conversation_memory_{agent_id}".format(
                agent_id=record.agent_id.replace(".", "_")
            ),
            default=memory_module.MemorySnapshot(),
        )
        self.skill_store = self._load_skill_store()
        self.skill_resolver = skills_resolver.SkillResolver(self.skill_store)
        self.turn_context_resolver = retrieval_turns.TurnContextResolver(
            retrieval_conversations.ConversationSemanticRetriever(
                conversations_root=self._conversation_root(),
                embeddings_root=self._embeddings_root(),
            )
        )
        self.memory_manager = memory_module.MemoryManager(
            agent_id=self.record.agent_id,
            model_name=self.model_name,
            config=self.memory,
        )
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

    def _resolve_model_name(
        self,
        model_name_override: str | None = None,
    ) -> tuple[str, str]:
        request_model = contracts_models.normalize_model_reference(
            model_name_override,
            model_backend=os.getenv("MODEL_BACKEND"),
        )
        if request_model:
            return request_model, "request"

        explicit_model = (self.definition.model or "").strip()
        if explicit_model:
            return explicit_model, "agent"

        env_model = contracts_models.normalize_model_reference(
            os.getenv("MODEL_NAME"),
            model_backend=os.getenv("MODEL_BACKEND"),
        )
        if env_model:
            return env_model, "env"

        return DEFAULT_MODEL, "default"

    def _resolve_model_timeout_seconds(self) -> float:
        raw_value = os.getenv(
            "MODEL_RESPONSE_TIMEOUT_SECONDS", str(DEFAULT_MODEL_TIMEOUT_SECONDS)
        )
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return DEFAULT_MODEL_TIMEOUT_SECONDS
        return value if value > 0 else DEFAULT_MODEL_TIMEOUT_SECONDS

    def _public_model_name(self, model_name: Optional[str] = None) -> str:
        label = contracts_models.public_model_label(model_name or self.model_name)
        if label:
            return label
        if self._model_source == "request":
            return "the selected model"
        if self._model_source == "agent":
            return "the agent model"
        if self._model_source == "env":
            return "the configured model"
        return "the default model"

    def _load_skill_store(self) -> skills_store.SkillStore:
        return skills_store.SkillStore(self.record.project_root / "skills")

    def _workspace_root(self) -> Path:
        return self.record.project_root.parent.parent

    def _conversation_root(self) -> Path:
        return self._workspace_root() / ".conversations"

    def _embeddings_root(self) -> Path:
        return self._workspace_root() / ".embeddings"

    def _build_adk_agent(self):
        instruction = runtime_prompts.build_agent_instruction(
            definition=self.definition,
            tool_definitions=tuple(self._tool_definitions.values()),
            execution=self.execution,
            additional_guidance=self.hooks.build_prompt_guidance(
                phase="direct", state={}
            ),
        )
        return runtime_adk.create_llm_agent(
            agent_id=self.record.agent_id,
            model=self.resolved_model.adk_model,
            instruction=instruction,
            tool_callables=list(self._tool_callables.values()),
            before_model_callback=self._before_model_callback,
            generate_content_config=self._build_generate_content_config(),
        )

    def _build_generate_content_config(
        self,
    ) -> types.GenerateContentConfig | None:
        if self.resolved_model.backend != "native":
            return None
        if not self.resolved_model.reference.startswith("gemini"):
            return None
        return runtime_adk.build_generate_content_config(
            model_name=self.resolved_model.reference,
            include_thoughts=True,
        )

    def _create_runner(self):
        return runtime_adk.create_runner(
            agent=self.agent,
            session_service=self._session_service,
        )

    def _before_model_callback(self, callback_context: Any, llm_request: Any) -> Any:
        runtime_prompts.apply_runtime_context(
            llm_request,
            self._ensure_turn_context_var().get(),
            conversation_history=self._conversation_history.get(),
            memory_snapshot=self._conversation_memory.get(),
        )
        return None

    def _missing_credentials_message(self) -> str:
        return (
            "Google API key is not configured. Set GOOGLE_API_KEY in the project .env "
            "before chatting with agents."
        )

    def _model_started_message(self, model_name: Optional[str] = None) -> str:
        active_model = self._public_model_name(model_name)
        return "Sending the request to {model}.".format(model=active_model)

    def _model_waiting_message(self, model_name: Optional[str] = None) -> str:
        active_model = self._public_model_name(model_name)
        return "Still waiting for a response from {model}.".format(model=active_model)

    def _model_timeout_message(self, model_name: Optional[str] = None) -> str:
        active_model = self._public_model_name(model_name)
        seconds = int(self.model_timeout_seconds)
        message = "Timed out waiting for {model} after {seconds} seconds.".format(
            model=active_model,
            seconds=seconds,
        )
        if self._model_source == "request":
            return (
                "{message} Leave the model selector on Default to fall back to the "
                "agent or environment default."
            ).format(
                message=message,
            )
        if self._model_source == "env" and self.model_name != DEFAULT_MODEL:
            return (
                "{message} The current .env sets a non-default model. Remove "
                "`MODEL_NAME` to fall back to the default runtime choice, or replace "
                "it with a model that responds for your account. If the default model "
                "also times out, check outbound network access and API key permissions."
            ).format(
                message=message,
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
                    model=self._public_model_name(model_name),
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
        usage: Optional[dict[str, Any]] = None,
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
                    "usage": usage,
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

    async def _emit_model_thinking(
        self,
        *,
        stream: stream_progress.EventStream,
        hook_state: contracts_hooks.HookState,
        thought_text: str = "",
        state: str = "running",
    ) -> None:
        merged_text = str(
            thought_text or hook_state.get("_model_thinking_text") or ""
        ).strip()
        if not merged_text:
            return
        hook_state["_model_thinking_text"] = merged_text
        await stream_progress.emit_thinking_step(
            step_id="model_thinking",
            label="Model thinking",
            detail=merged_text,
            state=state,
            agent_id=self.record.agent_id,
            source="model",
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
        conversation_id: Optional[str] = None,
        history: Optional[list[dict[str, Any]]] = None,
        stream: bool = True,
    ):
        active_conversation_id = conversation_id or request_context.current_conversation_id()
        active_session_id = session_id or str(uuid4())
        event_stream = stream_progress.EventStream()
        asyncio.create_task(
            self._run_chat(
                stream=event_stream,
                message=message,
                user_id=user_id,
                session_id=active_session_id,
                conversation_id=active_conversation_id,
                history=history or [],
                stream_output=stream,
            )
        )
        return active_session_id, event_stream.sse_messages()

    async def _run_chat(
        self,
        stream: stream_progress.EventStream,
        message: str,
        user_id: str,
        session_id: str,
        conversation_id: Optional[str] = None,
        history: Optional[list[dict[str, Any]]] = None,
        stream_output: bool = True,
    ) -> None:
        stream_token = stream_progress.bind_progress_stream(stream)
        resolved_token: Optional[contextvars.Token] = None
        turn_context_token: Optional[contextvars.Token] = None
        tool_guardrails_token: Optional[contextvars.Token] = None
        skill_store_token: Optional[contextvars.Token] = None
        history_token: Optional[contextvars.Token] = None
        memory_token: Optional[contextvars.Token] = None
        usage_aggregator = runtime_usage.UsageAggregator()
        hook_state = self.hooks.create_turn_state(
            agent_id=self.record.agent_id,
            user_id=user_id,
            session_id=session_id,
            message=message,
        )

        try:
            turn_context_var = self._ensure_turn_context_var()
            skill_store_token = skills_context.bind_skill_store(self.skill_store)
            tool_guardrails_token = self._tool_guardrails.set(
                guardrails_module.ToolLoopGuardrails(self.execution)
            )
            history_token = self._conversation_history.set(
                runtime_prompts.normalize_conversation_history(history or [])
            )
            await self.ensure_session(user_id=user_id, session_id=session_id)
            memory_snapshot = await self.memory_manager.prepare_turn(
                user_id=user_id,
                session_id=session_id,
                seed_history=self._conversation_history.get(),
            )
            memory_token = self._conversation_memory.set(memory_snapshot)
            turn_context = await self._prepare_turn(
                stream=stream,
                message=message,
                user_id=user_id,
                session_id=session_id,
                conversation_id=conversation_id,
                history=self._conversation_history.get(),
                memory_snapshot=memory_snapshot,
            )
            resolved_token = self._resolved_skills.set(turn_context.skills)
            turn_context_token = turn_context_var.set(turn_context)

            if not os.getenv("GOOGLE_API_KEY"):
                message_text = self._missing_credentials_message()
                await self._emit_terminal_error(
                    stream,
                    session_id=session_id,
                    message=message_text,
                    error="GOOGLE_API_KEY missing",
                    assistant_text=message_text,
                    usage=usage_aggregator.summary(),
                )
                return

            await self._execute_model_turn(
                stream=stream,
                message=message,
                user_id=user_id,
                session_id=session_id,
                resolved_context=turn_context.skills,
                hook_state=hook_state,
                stream_output=stream_output,
                usage_aggregator=usage_aggregator,
            )
            final_response_text = str(
                hook_state.get("_final_response_text") or ""
            ).strip()
            if self.memory.enabled and final_response_text:
                updated_memory = await self.memory_manager.record_turn(
                    user_id=user_id,
                    session_id=session_id,
                    user_message=message,
                    assistant_message=final_response_text,
                )
                self._conversation_memory.set(updated_memory)
            await stream.emit(
                "run_completed",
                {
                    "agent_id": self.record.agent_id,
                    "session_id": session_id,
                    "message": stream_messages.build_run_completed_message(
                        self.definition.name
                    ),
                },
            )
        except asyncio.TimeoutError:
            self.runner = self._create_runner()
            message_text = self._model_timeout_message()
            await self._emit_model_thinking(
                stream=stream,
                hook_state=hook_state,
                state="error",
            )
            await self._emit_terminal_error(
                stream,
                session_id=session_id,
                message=message_text,
                error="model_timeout",
                usage=usage_aggregator.summary(),
            )
        except Exception as exc:
            message_text = runtime_models.describe_model_error(
                exc,
                model_reference=self.model_name,
            )
            await self._emit_model_thinking(
                stream=stream,
                hook_state=hook_state,
                state="error",
            )
            await self._emit_terminal_error(
                stream,
                session_id=session_id,
                message=message_text,
                error="model_error",
                usage=usage_aggregator.summary(),
            )
        finally:
            if resolved_token is not None:
                self._resolved_skills.reset(resolved_token)
            if turn_context_token is not None:
                self._turn_context.reset(turn_context_token)
            if tool_guardrails_token is not None:
                self._tool_guardrails.reset(tool_guardrails_token)
            if skill_store_token is not None:
                skills_context.reset_skill_store(skill_store_token)
            if history_token is not None:
                self._conversation_history.reset(history_token)
            if memory_token is not None:
                self._conversation_memory.reset(memory_token)
            stream_progress.reset_progress_stream(stream_token)
            await stream.close()

    async def _prepare_turn(
        self,
        *,
        stream: stream_progress.EventStream,
        message: str,
        user_id: str,
        session_id: str,
        conversation_id: Optional[str],
        history: list[dict[str, str]],
        memory_snapshot: memory_module.MemorySnapshot,
    ) -> retrieval_turns.TurnContextBundle:
        await stream.emit(
            "run_started",
            {
                "agent_id": self.record.agent_id,
                "session_id": session_id,
                "user_id": user_id,
                "message": stream_messages.build_run_started_message(
                    self.definition.name
                ),
            },
        )
        await stream_progress.emit_thinking_step(
            step_id="understand_request",
            label="Understanding the question",
            detail="Working out the most reliable way to answer it.",
            state="running",
            agent_id=self.record.agent_id,
        )
        if history:
            await stream_progress.emit_thinking_step(
                step_id="conversation_context",
                label="Reviewing earlier messages",
                detail="Using recent conversation context so follow-up questions stay grounded.",
                state="done",
                agent_id=self.record.agent_id,
            )
        if self.memory.enabled and not memory_snapshot.is_empty:
            await stream_progress.emit_thinking_step(
                step_id="conversation_memory",
                label="Using compact conversation memory",
                detail="Carrying forward the important earlier facts and decisions without replaying the full transcript.",
                state="done",
                agent_id=self.record.agent_id,
            )
        turn_context = await asyncio.to_thread(
            self._resolve_turn_context,
            message,
            user_id,
            conversation_id,
            history,
        )
        await stream_progress.emit_debug_event(
            "skill_context_selected",
            agent_id=self.record.agent_id,
            skills=skills_resolver.serialize_resolved_skills(turn_context.skills),
            chunks=[
                {
                    "skill_id": chunk.skill_id,
                    "source": chunk.source,
                    "heading": chunk.heading,
                    "preview": chunk.text[:220],
                }
                for chunk in turn_context.skills.chunks
            ],
            conversations=retrieval_turns.serialize_recalled_conversations(
                turn_context
            ),
            message=retrieval_turns.describe_turn_context(turn_context),
        )
        skill_label, skill_detail, skill_state = runtime_prompts.skill_context_thinking(
            turn_context
        )
        await stream_progress.emit_thinking_step(
            step_id="guidance",
            label=skill_label,
            detail=skill_detail,
            state=skill_state,
            agent_id=self.record.agent_id,
        )
        if turn_context.recalled_conversations:
            await stream_progress.emit_thinking_step(
                step_id="semantic_memory",
                label="Recalling related conversations",
                detail="Pulled in a few older conversation excerpts that look relevant to this question.",
                state="done",
                agent_id=self.record.agent_id,
            )
        await stream_progress.emit_thinking_step(
            step_id="planning",
            label="Planning the approach",
            detail=runtime_prompts.planning_thinking_detail(turn_context),
            state="done",
            agent_id=self.record.agent_id,
        )
        return turn_context

    async def _execute_model_turn(
        self,
        *,
        stream: stream_progress.EventStream,
        message: str,
        user_id: str,
        session_id: str,
        resolved_context: skills_resolver.ResolvedSkillContext,
        hook_state: contracts_hooks.HookState,
        stream_output: bool,
        usage_aggregator: runtime_usage.UsageAggregator,
    ) -> str:
        await stream.emit(
            "model_started",
            {
                "agent_id": self.record.agent_id,
                "session_id": session_id,
                "model": self._public_model_name(),
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
        retry_attempt = 0
        while True:
            heartbeat_task = asyncio.create_task(
                self._emit_model_waiting_updates(stream, self.model_name)
            )
            saw_attempt_event = False
            try:
                user_content = types.Content(
                    role="user", parts=[types.Part(text=message)]
                )
                async with asyncio.timeout(self.model_timeout_seconds):
                    async for event in runtime_adk.stream_runner_events(
                        runner=self.runner,
                        user_id=user_id,
                        session_id=session_id,
                        new_message=user_content,
                        # Keep model-side streaming enabled so tool/thinking updates
                        # continue to arrive live even when assistant text deltas are off.
                        stream_output=True,
                    ):
                        saw_attempt_event = True
                        assistant_buffer = await self._handle_runner_event(
                            stream=stream,
                            event=event,
                            message=message,
                            resolved_context=resolved_context,
                            assistant_buffer=assistant_buffer,
                            hook_state=hook_state,
                            stream_output=stream_output,
                            usage_aggregator=usage_aggregator,
                        )
                return assistant_buffer
            except Exception as exc:
                should_retry = (
                    retry_attempt < MAX_TRANSIENT_MODEL_RETRIES
                    and not saw_attempt_event
                    and not assistant_buffer
                    and runtime_models.should_retry_model_error(exc)
                )
                if not should_retry:
                    raise

                retry_attempt += 1
                self.runner = self._create_runner()
                await stream_progress.emit_thinking_step(
                    step_id="answer",
                    label="Retrying after a model error",
                    detail="The model returned a temporary internal error, so the same step is being retried once.",
                    state="running",
                    agent_id=self.record.agent_id,
                )
                await asyncio.sleep(float(retry_attempt))
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
        stream_output: bool,
        usage_aggregator: runtime_usage.UsageAggregator,
    ) -> str:
        text = runtime_adk.extract_text(event)
        thought_text = runtime_adk.extract_thought_text(event)
        function_calls = list(event.get_function_calls() or [])
        function_responses = list(event.get_function_responses() or [])
        usage_aggregator.record_event(event)

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

        if thought_text:
            await self._emit_model_thinking(
                stream=stream,
                hook_state=hook_state,
                thought_text=runtime_adk.merge_streamed_text(
                    streamed_text=str(hook_state.get("_model_thinking_text") or ""),
                    final_event_text=thought_text,
                ),
                state="running",
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
            if stream_output:
                await stream.emit(
                    "assistant_delta",
                    {
                        "agent_id": self.record.agent_id,
                        "text": text,
                    },
                )
            return assistant_buffer

        if event.is_final_response():
            await self._emit_model_thinking(
                stream=stream,
                hook_state=hook_state,
                state="done",
            )

        if event.is_final_response() and (text or assistant_buffer):
            final_text = runtime_adk.merge_streamed_text(
                streamed_text=assistant_buffer,
                final_event_text=text,
            ).strip()
            final_text = self.hooks.finalize_response(text=final_text, state=hook_state)
            hook_state["_final_response_text"] = final_text
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
                    "usage": usage_aggregator.summary(),
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
                message=stream_messages.build_tool_selection_message(
                    call.name, selection_reason
                ),
            )
            await stream_progress.emit_debug_event(
                "tool_started",
                agent_id=self.record.agent_id,
                tool_name=call.name,
                args=call.args,
                message=stream_messages.build_tool_started_message(
                    call.name, call.args or {}
                ),
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

    def _resolve_skills(
        self,
        query: str,
        user_id: str,
        query_vector: Sequence[float] | None = None,
    ) -> skills_resolver.ResolvedSkillContext:
        return self.skill_resolver.resolve(
            query=query,
            user_id=user_id,
            behavior_ids=self.definition.behavior,
            knowledge_ids=self.definition.knowledge,
            query_vector=query_vector,
        )

    def _resolve_turn_context(
        self,
        query: str,
        user_id: str,
        conversation_id: str | None,
        history: Sequence[dict[str, str]] | None,
    ) -> retrieval_turns.TurnContextBundle:
        query_vector = self._shared_query_vector(query)
        try:
            skill_context = self._resolve_skills(
                query,
                user_id,
                query_vector=query_vector,
            )
        except TypeError:
            skill_context = self._resolve_skills(query, user_id)
        resolver = self._ensure_turn_context_resolver()
        return resolver.resolve(
            query=query,
            user_id=user_id,
            conversation_id=conversation_id,
            agent_id=self.record.agent_id,
            history=history,
            skill_context=skill_context,
            query_vector=query_vector,
        )

    def _shared_query_vector(
        self,
        query: str,
    ) -> tuple[float, ...] | None:
        semantic_retriever = getattr(
            getattr(getattr(self, "skill_resolver", None), "semantic", None),
            "retriever",
            None,
        )
        skill_provider = getattr(semantic_retriever, "provider", None)
        resolver = self._ensure_turn_context_resolver()
        conversation_provider = getattr(
            resolver.conversation_retriever.retriever,
            "provider",
            None,
        )
        if skill_provider is None or conversation_provider is None:
            return None
        if not bool(getattr(skill_provider, "is_available", False)):
            return None
        if not bool(getattr(conversation_provider, "is_available", False)):
            return None
        if (
            str(getattr(skill_provider, "name", "") or "").strip()
            != str(getattr(conversation_provider, "name", "") or "").strip()
            or str(getattr(skill_provider, "model_name", "") or "").strip()
            != str(getattr(conversation_provider, "model_name", "") or "").strip()
        ):
            return None
        try:
            if semantic_retriever is None:
                return None
            return tuple(semantic_retriever.embed_query(query) or ()) or None
        except Exception:
            return None

    def _ensure_turn_context_var(
        self,
    ) -> contextvars.ContextVar[retrieval_turns.TurnContextBundle]:
        context_var = getattr(self, "_turn_context", None)
        if context_var is not None:
            return context_var
        context_var = contextvars.ContextVar(
            "turn_context_{agent_id}".format(
                agent_id=self.record.agent_id.replace(".", "_")
            ),
            default=retrieval_turns.TurnContextBundle(),
        )
        self._turn_context = context_var
        return context_var

    def _ensure_turn_context_resolver(self) -> retrieval_turns.TurnContextResolver:
        resolver = getattr(self, "turn_context_resolver", None)
        if resolver is not None:
            return resolver
        resolver = retrieval_turns.TurnContextResolver(
            retrieval_conversations.ConversationSemanticRetriever(
                conversations_root=self._conversation_root(),
                embeddings_root=self._embeddings_root(),
            )
        )
        self.turn_context_resolver = resolver
        return resolver
