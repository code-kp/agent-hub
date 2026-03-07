import unittest

from core.stream.messages import (
    build_progress_message,
    build_skill_context_message,
    build_tool_completed_message,
    build_tool_selection_message,
    build_tool_started_message,
)
from core.skills.store import SkillChunk


class EventMessagesTest(unittest.TestCase):
    def test_progress_message_turns_metadata_into_readable_text(self) -> None:
        message = build_progress_message(
            "Searching indexed skill chunks.",
            query="refund policy",
            max_results=3,
        )

        self.assertIn("Searching indexed skill chunks.", message)
        self.assertIn('query="refund policy"', message)
        self.assertIn("max results=3", message)

    def test_skill_context_message_summarizes_selected_chunks(self) -> None:
        chunks = [
            SkillChunk(
                chunk_id="billing:1",
                skill_id="billing",
                source="billing.md",
                heading="Refunds",
                text="Refunds are allowed within 14 days.",
                tokens=("refund", "day"),
            ),
            SkillChunk(
                chunk_id="billing:2",
                skill_id="billing",
                source="billing.md",
                heading="Invoices",
                text="Invoices are emailed automatically.",
                tokens=("invoice",),
            ),
        ]

        message = build_skill_context_message(chunks)
        self.assertEqual(message, "Loaded 2 relevant skill excerpts from billing.md.")

    def test_tool_started_message_uses_inputs_not_raw_dict(self) -> None:
        message = build_tool_started_message(
            "search_skills",
            {"query": "refund policy", "max_results": 3},
        )

        self.assertIn("Running search_skills.", message)
        self.assertIn('query="refund policy"', message)
        self.assertIn("max results=3", message)

    def test_tool_completed_message_summarizes_known_shapes(self) -> None:
        self.assertEqual(
            build_tool_completed_message("search_skills", {"results": [{"id": 1}, {"id": 2}]}),
            "search_skills finished and found 2 result(s).",
        )
        self.assertEqual(
            build_tool_completed_message("get_current_utc_time", {"utc_time": "2026-03-07T12:00:00+00:00"}),
            "get_current_utc_time finished. Utc time: 2026-03-07T12:00:00+00:00.",
        )

    def test_tool_selection_message_is_plain_language(self) -> None:
        message = build_tool_selection_message(
            "search_skills",
            "The request mentions refunds and this tool can search the indexed skill library.",
        )

        self.assertEqual(
            message,
            "Choosing search_skills. The request mentions refunds and this tool can search the indexed skill library.",
        )


if __name__ == "__main__":
    unittest.main()
