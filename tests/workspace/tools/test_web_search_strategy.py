import unittest
from datetime import datetime, timezone

from workspace.tools.web_search_strategy import (
    build_search_plan,
    build_search_plan_detail,
)


class SearchPlanTest(unittest.TestCase):
    def test_build_search_plan_adds_current_date_for_temporal_query(self) -> None:
        plan = build_search_plan(
            "latest OpenAI news",
            now=datetime(2026, 3, 7, tzinfo=timezone.utc),
        )

        self.assertEqual(plan.effective_query, "latest OpenAI news March 7 2026")
        self.assertEqual(plan.current_date, "March 7 2026")
        self.assertTrue(plan.time_sensitive)

    def test_build_search_plan_keeps_non_temporal_query_unchanged(self) -> None:
        plan = build_search_plan(
            "how do refunds work",
            now=datetime(2026, 3, 7, tzinfo=timezone.utc),
        )

        self.assertEqual(plan.effective_query, "how do refunds work")
        self.assertFalse(plan.time_sensitive)

    def test_build_search_plan_detail_mentions_current_information_when_time_sensitive(
        self,
    ) -> None:
        plan = build_search_plan(
            "latest OpenAI news",
            now=datetime(2026, 3, 7, tzinfo=timezone.utc),
        )

        detail = build_search_plan_detail(plan)
        self.assertIn("latest OpenAI news March 7 2026", detail)
        self.assertIn("current information", detail)


if __name__ == "__main__":
    unittest.main()
