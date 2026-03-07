import tempfile
import unittest
from pathlib import Path

from core.skills.uploads import create_uploaded_skill


class SkillUploadsTest(unittest.TestCase):
    def test_create_uploaded_skill_normalizes_markdown_into_skill_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp)
            definition = create_uploaded_skill(
                skills_root=skills_root,
                file_name="Refund FAQ.md",
                content="# Refund FAQ\n\nRefunds are available within 30 days for annual plans.\n",
                uploader_id="browser-user",
                namespace="billing/policies",
                tags=("billing", "refund"),
                triggers=("refund", "annual plan"),
            )

            self.assertEqual(definition.id, "uploads.browser-user.billing.policies.refund-faq")
            self.assertEqual(
                definition.source,
                "uploads/browser-user/billing/policies/refund-faq.md",
            )
            self.assertEqual(definition.skill_type, "knowledge")
            self.assertEqual(definition.mode, "auto")
            self.assertEqual(definition.title, "Refund FAQ")
            self.assertIn("Refunds are available within 30 days", definition.body)
            self.assertIn("uploaded", definition.tags)
            self.assertIn("browser-user", definition.tags)

    def test_create_uploaded_skill_preserves_explicit_frontmatter_when_not_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp)
            definition = create_uploaded_skill(
                skills_root=skills_root,
                file_name="persona.md",
                content="""---
title: Premium Persona
type: persona
summary: Keep replies brief and polished.
tags: [persona, style]
mode: always_on
priority: 95
---

# Premium Persona

Reply briefly and keep a polished tone.
""",
                uploader_id="designer",
                namespace="profiles",
                skill_type="persona",
                mode="always_on",
            )

            self.assertEqual(definition.title, "Premium Persona")
            self.assertEqual(definition.skill_type, "persona")
            self.assertEqual(definition.mode, "always_on")
            self.assertEqual(definition.priority, 95)
            self.assertIn("style", definition.tags)


if __name__ == "__main__":
    unittest.main()
