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
            )

            self.assertEqual(
                definition.id, "uploads.browser-user.billing.policies.refund-faq"
            )
            self.assertEqual(
                definition.source,
                "uploads/browser-user/billing/policies/refund-faq.md",
            )
            self.assertEqual(definition.skill_class, "knowledge")
            self.assertEqual(definition.title, "Refund FAQ")
            self.assertIn("Refunds are available within 30 days", definition.body)

    def test_create_uploaded_skill_rewrites_markdown_without_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp)
            definition = create_uploaded_skill(
                skills_root=skills_root,
                file_name="persona.md",
                content="""# Premium Persona

Reply briefly and keep a polished tone.
""",
                uploader_id="designer",
                namespace="profiles",
            )

            self.assertEqual(definition.title, "Premium Persona")
            self.assertEqual(definition.skill_class, "knowledge")
            self.assertIn("polished tone", definition.summary)


if __name__ == "__main__":
    unittest.main()
