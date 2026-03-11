import unittest
from types import SimpleNamespace

from google.genai import types

import core.execution.shared.adk as shared_adk


class AdkHelpersTest(unittest.TestCase):
    def test_build_generate_content_config_uses_budget_for_gemini_2x(self) -> None:
        config = shared_adk.build_generate_content_config(
            model_name="gemini-2.5-flash",
            include_thoughts=True,
        )

        self.assertIsNotNone(config)
        self.assertTrue(config.thinking_config.include_thoughts)
        self.assertEqual(config.thinking_config.thinking_budget, -1)
        self.assertIsNone(config.thinking_config.thinking_level)

    def test_build_generate_content_config_uses_thinking_level_for_gemini_3x(self) -> None:
        config = shared_adk.build_generate_content_config(
            model_name="gemini-3.1-flash-lite-preview",
            include_thoughts=True,
        )

        self.assertIsNotNone(config)
        self.assertTrue(config.thinking_config.include_thoughts)
        self.assertEqual(config.thinking_config.thinking_level, types.ThinkingLevel.LOW)
        self.assertIsNone(config.thinking_config.thinking_budget)

    def test_extract_text_ignores_thought_parts_by_default(self) -> None:
        event = SimpleNamespace(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(text="Private reasoning", thought=True),
                    types.Part(text="Visible answer"),
                ],
            )
        )

        self.assertEqual(shared_adk.extract_text(event), "Visible answer")
        self.assertEqual(
            shared_adk.extract_text(event, include_thoughts=True),
            "Private reasoningVisible answer",
        )

    def test_extract_thought_text_returns_only_thought_parts(self) -> None:
        event = SimpleNamespace(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(text="Plan first.", thought=True),
                    types.Part(text="Then answer."),
                    types.Part(text="Double-check facts.", thought=True),
                ],
            )
        )

        self.assertEqual(
            shared_adk.extract_thought_text(event),
            "Plan first.Double-check facts.",
        )

    def test_merge_streamed_text_deduplicates_partial_overlap(self) -> None:
        self.assertEqual(
            shared_adk.merge_streamed_text(
                streamed_text="Hello wor",
                final_event_text="world",
            ),
            "Hello world",
        )

    def test_merge_streamed_text_keeps_full_stream_when_final_is_redundant(self) -> None:
        self.assertEqual(
            shared_adk.merge_streamed_text(
                streamed_text="The current UTC time is 20:32.",
                final_event_text="20:32.",
            ),
            "The current UTC time is 20:32.",
        )


if __name__ == "__main__":
    unittest.main()
