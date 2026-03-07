from __future__ import annotations

import asyncio
import contextlib
import contextvars
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

from core.event_messages import (
    build_error_message,
    build_run_completed_message,
    build_run_started_message,
    build_skill_context_message,
    build_tool_completed_message,
    build_tool_selection_message,
    build_tool_started_message,
)
from core.interfaces.agent import Agent
from core.interfaces.tools import build_adk_tools
from core.progress import (
    EventStream,
    bind_progress_stream,
    emit_progress,
    reset_progress_stream,
)
from core.registry import Register
from core.skill_store import SkillChunk, SkillStore


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


class AgentRuntime:
    def __init__(self, record: AgentRecord) -> None:
        self.record = record
        self.definition = Register.get(Agent, record.agent_name)
        self.model_name, self._model_source = self._resolve_model_name()
        self.model_timeout_seconds = self._resolve_model_timeout_seconds()
        self._tool_descriptions: Dict[str, str] = {
            tool.name: (tool.description or "")
            for tool in self.definition.tools
        }
        self._selected_chunks: contextvars.ContextVar[List[SkillChunk]] = contextvars.ContextVar(
            "selected_chunks_{agent_id}".format(agent_id=record.agent_id.replace(".", "_")),
            default=[],
        )
        self.skill_store = self._load_skill_store(self.definition.skills_dir)
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

    def _load_skill_store(self, skills_dir: Optional[str]) -> Optional[SkillStore]:
        if not skills_dir:
            return None
        directory = Path(skills_dir)
        if not directory.is_absolute():
            candidates = []
            if directory.parts and directory.parts[0] == "skills":
                candidates.append(self.record.project_root / directory)
            else:
                candidates.append(self.record.project_root / "skills" / directory)
                candidates.append(self.record.project_root / directory)

            for candidate in candidates:
                if candidate.exists():
                    directory = candidate
                    break
            else:
                directory = candidates[0]
        return SkillStore(directory)

    def _build_adk_agent(self) -> LlmAgent:
        instruction = "\n\n".join(
            part
            for part in [
                "Agent name: {name}".format(name=self.definition.name),
                "Agent description: {description}".format(description=self.definition.description),
                self.definition.system_prompt.strip(),
                "Use tools when they improve accuracy and keep responses concise.",
            ]
            if part
        )
        return LlmAgent(
            name=self.record.agent_id.replace(".", "_"),
            model=self.model_name,
            instruction=instruction,
            tools=build_adk_tools(self.definition.tools),
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
                await stream.emit(
                    "model_waiting",
                    {
                        "agent_id": self.record.agent_id,
                        "model": model_name or self.model_name,
                        "message": self._model_waiting_message(model_name),
                    },
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
        selected_chunks = self._selected_chunks.get()
        if not selected_chunks:
            return None

        config = getattr(llm_request, "config", None)
        if config is None:
            return None

        skill_prompt = self._format_skill_context(selected_chunks)
        if not skill_prompt:
            return None

        system_instruction = config.system_instruction or types.Content(role="system", parts=[])
        if not isinstance(system_instruction, types.Content):
            system_instruction = types.Content(
                role="system",
                parts=[types.Part(text=str(system_instruction))],
            )
        if not system_instruction.parts:
            system_instruction.parts.append(types.Part(text=""))

        marker = "Relevant skill excerpts for this turn:"
        existing = system_instruction.parts[0].text or ""
        if marker not in existing:
            system_instruction.parts[0].text = "{existing}\n\n{skill_prompt}".format(
                existing=existing.strip(),
                skill_prompt=skill_prompt,
            ).strip()
            config.system_instruction = system_instruction
        return None

    def _format_skill_context(self, chunks: List[SkillChunk]) -> str:
        if not chunks:
            return ""
        lines = [
            "Relevant skill excerpts for this turn:",
            "Use this context only when relevant to the user question.",
        ]
        for chunk in chunks:
            lines.append("[{label}]".format(label=chunk.label))
            lines.append(chunk.text)
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
        selected_token: Optional[contextvars.Token] = None
        selected_chunks: List[SkillChunk] = []

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
            selected_chunks = await asyncio.to_thread(self._select_chunks, message)
            selected_token = self._selected_chunks.set(selected_chunks)
            await emit_progress(
                "skill_context_selected",
                agent_id=self.record.agent_id,
                chunks=[
                    {
                        "source": chunk.source,
                        "heading": chunk.heading,
                        "preview": chunk.text[:220],
                    }
                    for chunk in selected_chunks
                ],
                message=build_skill_context_message(selected_chunks),
            )

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
                                selected_chunks=selected_chunks,
                                model_hint=text,
                            )
                            await stream.emit(
                                "tool_selection_reason",
                                {
                                    "agent_id": self.record.agent_id,
                                    "tool_name": call.name,
                                    "reason": selection_reason,
                                    "message": build_tool_selection_message(call.name, selection_reason),
                                },
                            )
                            await stream.emit(
                                "tool_started",
                                {
                                    "agent_id": self.record.agent_id,
                                    "tool_name": call.name,
                                    "args": call.args,
                                    "message": build_tool_started_message(call.name, call.args or {}),
                                },
                            )

                        for response in function_responses:
                            await stream.emit(
                                "tool_completed",
                                {
                                    "agent_id": self.record.agent_id,
                                    "tool_name": response.name,
                                    "response": response.response,
                                    "message": build_tool_completed_message(
                                        response.name,
                                        response.response,
                                    ),
                                },
                            )

                        if getattr(event, "partial", False) and text:
                            assistant_buffer += text
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
                            await stream.emit(
                                "assistant_message",
                                {
                                    "agent_id": self.record.agent_id,
                                    "text": final_text,
                                },
                            )
                        elif not function_calls and not function_responses:
                            await stream.emit(
                                "agent_event",
                                {
                                    "agent_id": self.record.agent_id,
                                    "author": getattr(event, "author", None),
                                    "event_id": getattr(event, "id", None),
                                },
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
            if selected_token is not None:
                self._selected_chunks.reset(selected_token)
            reset_progress_stream(stream_token)
            await stream.close()

    def _select_chunks(self, query: str) -> List[SkillChunk]:
        if self.skill_store is None:
            return []
        return self.skill_store.select_relevant_chunks(query=query)

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
