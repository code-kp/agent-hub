import tempfile
import unittest
from pathlib import Path

from core.skills.store import SkillStore


class SkillStoreTest(unittest.TestCase):
    def test_chunking_and_retrieval_prefers_relevant_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_dir = Path(tmp)
            (skills_dir / "billing.md").write_text(
                """---
title: Billing Knowledge
type: knowledge
summary: Refund and invoice guidance.
tags: [billing, refund, invoice]
triggers: [refund, invoice]
mode: auto
priority: 70
---

# Billing

## Refunds

Refunds are allowed within 14 days.

## Invoices

Invoices are emailed automatically.
""",
                encoding="utf-8",
            )
            (skills_dir / "api.md").write_text(
                """---
title: API Knowledge
type: knowledge
summary: API rate limit guidance.
tags: [api, rate limits]
triggers: [rate limit]
mode: auto
priority: 60
---

# API

## Rate Limits

The API allows 100 requests per minute per key.
""",
                encoding="utf-8",
            )

            store = SkillStore(skills_dir)
            results = store.select_relevant_chunks("What is the refund policy?", max_chunks=2)

            self.assertTrue(results)
            self.assertEqual(results[0].skill_id, "billing")
            self.assertEqual(results[0].source, "billing.md")
            self.assertIn("Refunds", results[0].heading)
            self.assertIn("14 days", results[0].text)


if __name__ == "__main__":
    unittest.main()
