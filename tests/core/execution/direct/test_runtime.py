import asyncio
import contextvars
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from google.adk.agents.run_config import StreamingMode
from google.genai import types

from api import _parse_sse_frame
from core.contracts.agent import Agent
from core.contracts.execution import DEFAULT_EXECUTION_CONFIG
from core.contracts.memory import DEFAULT_MEMORY_CONFIG
from core.memory.context import MemorySnapshot
from core.stream.progress import EventStream
from core.skills.resolver import ResolvedSkillContext
from core.execution import AgentRecord, DirectAgentRuntime


class _NeverRespondingRunner:
    async def run_async(self, **kwargs):
        await asyncio.sleep(3600)
        if False:
            yield None


class _FailingRunner:
    def __init__(self, message: str) -> None:
        self.message = message

    async def run_async(self, **kwargs):
        raise RuntimeError(self.message)
        if False:
            yield None


class _StreamingRunner:
    def __init__(self) -> None:
        self.last_kwargs = None

    async def run_async(self, **kwargs):
        self.last_kwargs = kwargs
        yield _FakeEvent(partial=True, text="Hello ")
        yield _FakeEvent(
            final=True,
            text="Hello world",
            usage_metadata=SimpleNamespace(
                prompt_token_count=18,
                candidates_token_count=7,
                tool_use_prompt_token_count=3,
                thoughts_token_count=2,
                cached_content_token_count=0,
                total_token_count=30,
            ),
        )


class _ThinkingRunner:
    def __init__(self) -> None:
        self.last_kwargs = None

    async def run_async(self, **kwargs):
        self.last_kwargs = kwargs
        yield _FakeEvent(
            partial=True,
            parts=[types.Part(text="Compare the options carefully.", thought=True)],
        )
        yield _FakeEvent(partial=True, text="Hello ")
        yield _FakeEvent(
            final=True,
            parts=[
                types.Part(
                    text="Compare the options carefully. Keep the reply short.",
                    thought=True,
                ),
                types.Part(text="Hello world"),
            ],
        )


class _FakeEvent:
    def __init__(
        self,
        *,
        partial: bool = False,
        final: bool = False,
        text: str = "",
        parts=None,
        usage_metadata=None,
    ) -> None:
        self.partial = partial
        self._final = final
        self.content = types.Content(
            role="model",
            parts=list(parts or [types.Part(text=text)]),
        )
        self.author = "test-agent"
        self.id = "event-1"
        self.model_version = "gemini-test"
        self.usage_metadata = usage_metadata

    def get_function_calls(self):
        return []

    def get_function_responses(self):
        return []

    def is_final_response(self) -> bool:
        return self._final


class DirectRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_missing_google_api_key_emits_error_and_closes_stream(self) -> None:
        runtime = self._build_runtime()
        stream = EventStream()

        with patch.dict(os.environ, {"GOOGLE_API_KEY": ""}, clear=False):
            await runtime._run_chat(
                stream=stream,
                message="Hello",
                user_id="test-user",
                session_id="session-1",
            )

        events = await self._collect_events(stream)
        event_types = [event["type"] for event in events]

        self.assertIn("run_started", event_types)
        self.assertIn("thinking_step", event_types)
        self.assertEqual(event_types[-2], "assistant_message")
        self.assertEqual(event_types[-1], "error")
        self.assertIn("Google API key is not configured", events[-2]["text"])
        self.assertIn("Google API key is not configured", events[-1]["message"])

    async def test_model_timeout_emits_error_event(self) -> None:
        runtime = self._build_runtime()
        runtime.runner = _NeverRespondingRunner()
        runtime.model_timeout_seconds = 0.01
        stream = EventStream()

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=False):
            await runtime._run_chat(
                stream=stream,
                message="Hello",
                user_id="test-user",
                session_id="session-2",
            )

        events = await self._collect_events(stream)
        event_types = [event["type"] for event in events]

        self.assertIn("run_started", event_types)
        self.assertIn("model_started", event_types)
        self.assertIn("thinking_step", event_types)
        self.assertEqual(event_types[-1], "error")
        self.assertEqual(events[-1]["error"], "model_timeout")
        self.assertIn("Timed out waiting for", events[-1]["message"])
        self.assertNotIn("assistant_message", event_types)

    async def test_stream_false_buffers_answer_until_final_message(self) -> None:
        runtime = self._build_runtime()
        runtime.runner = _StreamingRunner()
        runtime.agent = SimpleNamespace(name="test-agent")
        stream = EventStream()

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=False):
            await runtime._run_chat(
                stream=stream,
                message="Hello",
                user_id="test-user",
                session_id="session-4",
                stream_output=False,
            )

        events = await self._collect_events(stream)
        event_types = [event["type"] for event in events]

        self.assertNotIn("assistant_delta", event_types)
        self.assertEqual(events[-2]["type"], "assistant_message")
        self.assertEqual(events[-2]["text"], "Hello world")
        self.assertEqual(events[-1]["type"], "run_completed")
        self.assertEqual(
            runtime.runner.last_kwargs["run_config"].streaming_mode,
            StreamingMode.SSE,
        )

    async def test_stream_true_emits_deltas_and_deduplicates_final_text(self) -> None:
        runtime = self._build_runtime()
        runtime.runner = _StreamingRunner()
        runtime.agent = SimpleNamespace(name="test-agent")
        stream = EventStream()

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=False):
            await runtime._run_chat(
                stream=stream,
                message="Hello",
                user_id="test-user",
                session_id="session-5",
                stream_output=True,
            )

        events = await self._collect_events(stream)
        delta_text = "".join(
            event["text"] for event in events if event["type"] == "assistant_delta"
        )
        final_message = next(
            event for event in events if event["type"] == "assistant_message"
        )

        self.assertEqual(delta_text, "Hello ")
        self.assertEqual(final_message["text"], "Hello world")
        self.assertEqual(final_message["usage"]["input_tokens"], 18)
        self.assertEqual(final_message["usage"]["output_tokens"], 7)
        self.assertEqual(final_message["usage"]["tool_use_prompt_tokens"], 3)
        self.assertEqual(final_message["usage"]["total_tokens"], 30)
        self.assertEqual(final_message["usage"]["call_count"], 1)
        self.assertEqual(
            runtime.runner.last_kwargs["run_config"].streaming_mode,
            StreamingMode.SSE,
        )

    async def test_model_thoughts_emit_thinking_steps_without_entering_answer_text(self) -> None:
        runtime = self._build_runtime()
        runtime.runner = _ThinkingRunner()
        runtime.agent = SimpleNamespace(name="test-agent")
        stream = EventStream()

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=False):
            await runtime._run_chat(
                stream=stream,
                message="Hello",
                user_id="test-user",
                session_id="session-7",
                stream_output=False,
            )

        events = await self._collect_events(stream)
        model_thought_events = [
            event
            for event in events
            if event["type"] == "thinking_step" and event.get("source") == "model"
        ]
        final_message = next(
            event for event in events if event["type"] == "assistant_message"
        )

        self.assertGreaterEqual(len(model_thought_events), 2)
        self.assertEqual(final_message["text"], "Hello world")
        self.assertNotIn("Compare the options", final_message["text"])
        self.assertEqual(model_thought_events[-1]["state"], "done")
        self.assertIn("Keep the reply short.", model_thought_events[-1]["detail"])

    async def test_timeout_message_points_to_env_model_override(self) -> None:
        runtime = self._build_runtime()
        runtime.runner = _NeverRespondingRunner()
        runtime.model_name = "env-model"
        runtime._model_source = "env"
        runtime.model_timeout_seconds = 0.01
        stream = EventStream()

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=False):
            await runtime._run_chat(
                stream=stream,
                message="Hello",
                user_id="test-user",
                session_id="session-3",
            )

        events = await self._collect_events(stream)
        error_event = events[-1]

        self.assertEqual(error_event["type"], "error")
        self.assertIn("MODEL_NAME", error_event["message"])
        self.assertIn("env-model", error_event["message"])
        self.assertIn("gemini-2.0-flash", error_event["message"])

    def test_model_name_uses_litellm_prefix_when_backend_env_requests_it(self) -> None:
        runtime = self._build_runtime()
        runtime.definition = Agent(
            name="General Assistant",
            description="Test agent",
            system_prompt="Test prompt",
            tools=(),
            model=None,
        )

        with patch.dict(
            os.environ,
            {"MODEL_NAME": "openai/gpt-4o-mini", "MODEL_BACKEND": "litellm"},
            clear=False,
        ):
            model_name, source = runtime._resolve_model_name()

        self.assertEqual(model_name, "litellm:openai/gpt-4o-mini")
        self.assertEqual(source, "env")

    def test_model_name_prefers_request_override_over_env(self) -> None:
        runtime = self._build_runtime()
        runtime.definition = Agent(
            name="General Assistant",
            description="Test agent",
            system_prompt="Test prompt",
            tools=(),
            model=None,
        )

        with patch.dict(
            os.environ,
            {"MODEL_NAME": "gemini-2.0-flash", "MODEL_BACKEND": "litellm"},
            clear=False,
        ):
            model_name, source = runtime._resolve_model_name("openai/gpt-4o-mini")

        self.assertEqual(model_name, "litellm:openai/gpt-4o-mini")
        self.assertEqual(source, "request")

    async def test_model_provider_error_is_sanitized_and_not_sent_as_assistant_message(self) -> None:
        runtime = self._build_runtime()
        runtime.runner = _FailingRunner(
            "Failed to load vertex credentials. Your default credentials were not found."
        )
        runtime.model_name = "litellm:gemini/gemini-2.0-flash"
        stream = EventStream()

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=False):
            await runtime._run_chat(
                stream=stream,
                message="Hello",
                user_id="test-user",
                session_id="session-6",
            )

        events = await self._collect_events(stream)
        event_types = [event["type"] for event in events]
        error_event = events[-1]

        self.assertNotIn("assistant_message", event_types)
        self.assertEqual(error_event["type"], "error")
        self.assertEqual(error_event["error"], "model_error")
        self.assertIn("Google AI Studio", error_event["message"])
        self.assertNotIn("Traceback", error_event["message"])

    async def test_transient_internal_model_error_retries_once_before_failing(self) -> None:
        runtime = self._build_runtime()
        streaming_runner = _StreamingRunner()
        runtime.runner = _FailingRunner(
            "500 INTERNAL. {'error': {'code': 500, 'message': 'Internal error encountered.', 'status': 'INTERNAL'}}."
        )
        runtime._create_runner = lambda: streaming_runner
        runtime.agent = SimpleNamespace(name="test-agent")
        stream = EventStream()

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=False):
            await runtime._run_chat(
                stream=stream,
                message="Hello",
                user_id="test-user",
                session_id="session-8",
                stream_output=True,
            )

        events = await self._collect_events(stream)
        event_types = [event["type"] for event in events]
        retry_event = next(
            event
            for event in events
            if event["type"] == "thinking_step"
            and event["label"] == "Retrying after a model error"
        )
        final_message = next(
            event for event in events if event["type"] == "assistant_message"
        )

        self.assertNotIn("error", event_types)
        self.assertIn("temporary internal error", retry_event["detail"])
        self.assertEqual(final_message["text"], "Hello world")

    def _build_runtime(self) -> DirectAgentRuntime:
        runtime = object.__new__(DirectAgentRuntime)
        runtime.record = AgentRecord(
            agent_id="general",
            module_name="workspace.agents.general",
            agent_name="General Assistant",
            project_name="general",
            project_root=Path("."),
            fingerprint="test",
        )
        runtime.definition = Agent(
            name="General Assistant",
            description="Test agent",
            system_prompt="Test prompt",
            tools=(),
            model=None,
        )
        runtime.model_name = "gemini-test"
        runtime._model_source = "default"
        runtime.model_timeout_seconds = 60.0
        runtime._tool_definitions = {}
        runtime._tool_callables = {}
        runtime._tool_descriptions = {}
        runtime._resolved_skills = contextvars.ContextVar(
            "resolved_skills_test",
            default=ResolvedSkillContext(),
        )
        runtime._tool_guardrails = contextvars.ContextVar(
            "tool_guardrails_test",
            default=None,
        )
        runtime._conversation_history = contextvars.ContextVar(
            "conversation_history_test",
            default=[],
        )
        runtime.skill_store = None
        runtime.skill_resolver = object()
        runtime._session_service = object()
        runtime._session_keys = set()
        runtime.execution = DEFAULT_EXECUTION_CONFIG
        runtime.memory = DEFAULT_MEMORY_CONFIG
        runtime.hooks = runtime.definition.hooks
        runtime.agent = object()
        runtime.runner = _NeverRespondingRunner()
        runtime.ensure_session = AsyncMock(return_value=None)
        runtime._resolve_skills = lambda query, user_id: ResolvedSkillContext()
        runtime.memory_manager = SimpleNamespace(
            prepare_turn=AsyncMock(return_value=MemorySnapshot()),
            record_turn=AsyncMock(return_value=MemorySnapshot()),
        )
        runtime._conversation_memory = contextvars.ContextVar(
            "conversation_memory_test",
            default=MemorySnapshot(),
        )
        runtime._create_runner = lambda: runtime.runner
        return runtime

    async def _collect_events(self, stream: EventStream):
        events = []
        async for frame in stream.sse_messages():
            parsed = _parse_sse_frame(frame)
            if parsed is not None:
                events.append(parsed)
        return events


if __name__ == "__main__":
    unittest.main()
