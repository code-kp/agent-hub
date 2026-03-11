import unittest

import unittest.mock as mock

from api import AgentApi, _parse_sse_frame


class ParseSseFrameTest(unittest.TestCase):
    def test_parses_event_type_and_json_payload(self) -> None:
        parsed = _parse_sse_frame('event: thinking_step\ndata: {"label":"Working"}\n\n')

        self.assertEqual(parsed, {"label": "Working", "type": "thinking_step"})

    def test_wraps_non_json_payload_as_error_message(self) -> None:
        parsed = _parse_sse_frame("data: not-json\n\n")

        self.assertEqual(parsed["type"], "message")
        self.assertEqual(parsed["message"], "Failed to parse stream payload.")
        self.assertEqual(parsed["raw"], "not-json")


class AgentApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_stream_chat_events_forwards_stream_flag(self) -> None:
        async def fake_stream():
            yield 'event: assistant_message\ndata: {"text":"done"}\n\n'

        platform = mock.Mock()
        platform.stream_chat = mock.AsyncMock(
            return_value=("web.answer", "orchestrated", "session-1", fake_stream())
        )
        api = AgentApi(platform)

        _, mode, _, events_iter = await api.stream_chat_events(
            message="hello",
            agent_id="web.answer",
            mode="orchestrated",
            model_name="gemini-2.0-flash",
            user_id="api-user",
            session_id="session-1",
            stream=False,
        )
        events = [event async for event in events_iter]

        platform.stream_chat.assert_awaited_once_with(
            agent_id="web.answer",
            mode="orchestrated",
            model_name="gemini-2.0-flash",
            message="hello",
            user_id="api-user",
            session_id="session-1",
            stream=False,
        )
        self.assertEqual(mode, "orchestrated")
        self.assertEqual(events[0]["type"], "assistant_message")


if __name__ == "__main__":
    unittest.main()
