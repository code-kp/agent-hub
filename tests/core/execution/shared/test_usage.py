import unittest
from types import SimpleNamespace

from core.execution.shared.usage import UsageAggregator


class _FakeEvent:
    def __init__(
        self,
        *,
        event_id: str,
        partial: bool = False,
        text: str = "",
        function_calls=None,
        usage_metadata=None,
        author: str = "planner_agent",
        model_version: str = "gemini-2.0-flash",
    ) -> None:
        self.id = event_id
        self.partial = partial
        self.author = author
        self.model_version = model_version
        self.usage_metadata = usage_metadata
        self.interaction_id = None
        self.error_code = None
        self.finish_reason = None
        self.turn_complete = False
        self.content = (
            SimpleNamespace(parts=[SimpleNamespace(text=text)]) if text else None
        )
        self._function_calls = function_calls or []

    def get_function_calls(self):
        return self._function_calls


class UsageAggregatorTest(unittest.TestCase):
    def test_aggregates_multiple_non_partial_model_calls(self) -> None:
        aggregator = UsageAggregator()

        aggregator.record_event(
            _FakeEvent(
                event_id="planner-1",
                text="planning",
                usage_metadata=SimpleNamespace(
                    prompt_token_count=120,
                    candidates_token_count=25,
                    tool_use_prompt_token_count=0,
                    thoughts_token_count=4,
                    cached_content_token_count=0,
                    total_token_count=149,
                ),
                author="planner_agent",
            )
        )
        aggregator.record_event(
            _FakeEvent(
                event_id="executor-1",
                function_calls=[{"name": "search_web"}],
                usage_metadata=SimpleNamespace(
                    prompt_token_count=180,
                    candidates_token_count=18,
                    tool_use_prompt_token_count=22,
                    thoughts_token_count=3,
                    cached_content_token_count=0,
                    total_token_count=223,
                ),
                author="executor_agent",
            )
        )

        summary = aggregator.summary()

        self.assertIsNotNone(summary)
        self.assertEqual(summary["call_count"], 2)
        self.assertEqual(summary["input_tokens"], 300)
        self.assertEqual(summary["output_tokens"], 43)
        self.assertEqual(summary["tool_use_prompt_tokens"], 22)
        self.assertEqual(summary["thoughts_tokens"], 7)
        self.assertEqual(summary["total_tokens"], 372)
        self.assertEqual(summary["calls"][0]["author"], "planner_agent")
        self.assertEqual(summary["calls"][1]["author"], "executor_agent")

    def test_ignores_partial_and_duplicate_events(self) -> None:
        aggregator = UsageAggregator()
        usage = SimpleNamespace(
            prompt_token_count=50,
            candidates_token_count=10,
            tool_use_prompt_token_count=0,
            thoughts_token_count=0,
            cached_content_token_count=0,
            total_token_count=60,
        )

        aggregator.record_event(
            _FakeEvent(
                event_id="writer-partial",
                partial=True,
                text="Hello ",
                usage_metadata=usage,
            )
        )
        aggregator.record_event(
            _FakeEvent(
                event_id="writer-final",
                text="Hello world",
                usage_metadata=usage,
                author="writer_agent",
            )
        )
        aggregator.record_event(
            _FakeEvent(
                event_id="writer-final",
                text="Hello world",
                usage_metadata=usage,
                author="writer_agent",
            )
        )

        summary = aggregator.summary()

        self.assertIsNotNone(summary)
        self.assertEqual(summary["call_count"], 1)
        self.assertEqual(summary["input_tokens"], 50)
        self.assertEqual(summary["output_tokens"], 10)
        self.assertEqual(summary["total_tokens"], 60)


if __name__ == "__main__":
    unittest.main()
