import asyncio
import contextvars
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from api import _parse_sse_frame
from core.contracts.agent import Agent
from core.contracts.execution import DEFAULT_EXECUTION_CONFIG
from core.stream.progress import EventStream
from core.skills.resolver import ResolvedSkillContext
from core.execution import AgentRecord, DirectAgentRuntime


class _NeverRespondingRunner:
    async def run_async(self, **kwargs):
        await asyncio.sleep(3600)
        if False:
            yield None


class RuntimeGuardrailsTest(unittest.IsolatedAsyncioTestCase):
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

        self.assertEqual(event_types[0], "run_started")
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

        self.assertEqual(event_types[0], "run_started")
        self.assertIn("model_started", event_types)
        self.assertIn("thinking_step", event_types)
        self.assertEqual(event_types[-2], "assistant_message")
        self.assertEqual(event_types[-1], "error")
        self.assertEqual(events[-1]["error"], "model_timeout")
        self.assertIn("Timed out waiting for", events[-2]["text"])
        self.assertIn("Timed out waiting for", events[-1]["message"])

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
            skills_dir=None,
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
        runtime.skill_store = None
        runtime.skill_resolver = object()
        runtime._session_service = object()
        runtime._session_keys = set()
        runtime.execution = DEFAULT_EXECUTION_CONFIG
        runtime.hooks = runtime.definition.hooks
        runtime.agent = object()
        runtime.runner = _NeverRespondingRunner()
        runtime.ensure_session = AsyncMock(return_value=None)
        runtime._resolve_skills = lambda query, user_id: ResolvedSkillContext()
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
