import tempfile
import unittest
from pathlib import Path

from core.skills.resolver import SkillResolver
from core.skills.store import SkillStore


class SkillResolverTest(unittest.TestCase):
    def test_resolver_uses_explicit_behavior_and_knowledge_skill_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp)
            self._write(
                skills_root / "behavior" / "support" / "persona.md",
                """# Support Persona

Keep support replies concrete and operational.
""",
            )
            self._write(
                skills_root / "knowledge" / "support" / "triage.md",
                """# Support Triage

If production is affected, provide mitigation first.
""",
            )
            self._write(
                skills_root / "knowledge" / "general" / "product.md",
                """# Product Knowledge

General product details.
""",
            )

            resolver = SkillResolver(SkillStore(skills_root))
            context = resolver.resolve(
                query="We have a production incident and need troubleshooting guidance.",
                user_id="support-user",
                behavior_ids=("support.persona",),
                knowledge_ids=("support.triage",),
            )

            self.assertEqual(
                [skill.id for skill in context.behavior], ["support.persona"]
            )
            self.assertEqual(
                [skill.id for skill in context.knowledge], ["support.triage"]
            )
            self.assertTrue(context.chunks)
            self.assertTrue(
                all(
                    chunk.skill_id in {"support.persona", "support.triage"}
                    for chunk in context.chunks
                )
            )

    def test_resolver_limits_uploaded_skills_to_matching_user_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp)
            self._write(
                skills_root / "behavior" / "support" / "persona.md",
                """# Support Persona

Be concrete and operational.
""",
            )
            self._write(
                skills_root / "uploads" / "browser-user" / "refund-policy.md",
                """# Refund Policy

Refunds are available within 30 days for annual plans.
""",
            )

            resolver = SkillResolver(SkillStore(skills_root))
            matching_context = resolver.resolve(
                query="What is the refund timeline for annual plans?",
                user_id="browser-user",
                behavior_ids=("support.persona",),
                knowledge_ids=(),
            )
            other_user_context = resolver.resolve(
                query="What is the refund timeline for annual plans?",
                user_id="another-user",
                behavior_ids=("support.persona",),
                knowledge_ids=(),
            )

            self.assertEqual(
                [skill.id for skill in matching_context.behavior], ["support.persona"]
            )
            self.assertEqual(
                [skill.id for skill in matching_context.knowledge],
                ["uploads.browser-user.refund-policy"],
            )
            self.assertTrue(
                any(
                    chunk.skill_id == "uploads.browser-user.refund-policy"
                    for chunk in matching_context.chunks
                )
            )
            self.assertEqual(
                [skill.id for skill in other_user_context.behavior], ["support.persona"]
            )
            self.assertEqual(other_user_context.knowledge, ())
            self.assertTrue(
                all(
                    chunk.skill_id == "support.persona"
                    for chunk in other_user_context.chunks
                )
            )

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
