import tempfile
import unittest
from pathlib import Path

from core.skills.store import SkillStore


class SkillStoreTest(unittest.TestCase):
    def test_chunking_and_retrieval_prefers_relevant_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_dir = Path(tmp)
            (skills_dir / "knowledge" / "billing.md").parent.mkdir(parents=True, exist_ok=True)
            (skills_dir / "knowledge" / "billing.md").write_text(
                """# Billing

## Refunds

Refunds are allowed within 14 days.

## Invoices

Invoices are emailed automatically.
""",
                encoding="utf-8",
            )
            (skills_dir / "knowledge" / "api.md").write_text(
                """# API

## Rate Limits

The API allows 100 requests per minute per key.
""",
                encoding="utf-8",
            )

            store = SkillStore(skills_dir)
            results = store.select_relevant_chunks("What is the refund policy?", max_chunks=2)

            self.assertTrue(results)
            self.assertEqual(results[0].skill_id, "billing")
            self.assertEqual(results[0].source, "knowledge/billing.md")
            self.assertIn("Refunds", results[0].heading)
            self.assertIn("14 days", results[0].text)


if __name__ == "__main__":
    unittest.main()
