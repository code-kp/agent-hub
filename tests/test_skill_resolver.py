import tempfile
import unittest
from pathlib import Path

from core.skills.resolver import SkillResolver
from core.skills.store import SkillStore


class SkillResolverTest(unittest.TestCase):
    def test_resolver_keeps_always_on_skills_and_selects_relevant_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp)
            self._write(
                skills_root / "support" / "persona.md",
                """---
title: Support Persona
type: persona
summary: Keep support replies concrete and operational.
tags: [support, persona]
triggers: [debug]
mode: always_on
priority: 100
---

# Support Persona

Be concrete and operational.
""",
            )
            self._write(
                skills_root / "support" / "triage.md",
                """---
title: Support Triage
type: workflow
summary: Troubleshoot incidents and escalation paths.
tags: [support, incident, escalation]
triggers: [incident, production, troubleshoot]
mode: auto
priority: 90
---

# Support Triage

If production is affected, provide mitigation first.
""",
            )
            self._write(
                skills_root / "general" / "product.md",
                """---
title: Product Knowledge
type: knowledge
summary: General product information.
tags: [product]
triggers: [product]
mode: auto
priority: 50
---

# Product

General product details.
""",
            )

            resolver = SkillResolver(SkillStore(skills_root))
            context = resolver.resolve(
                query="We have a production incident and need troubleshooting guidance.",
                user_id="support-user",
                skill_scopes=("support",),
                always_on_skill_ids=(),
            )

            self.assertEqual([skill.id for skill in context.always_on_skills], ["support.persona"])
            self.assertEqual([skill.id for skill in context.selected_skills], ["support.triage"])
            self.assertTrue(context.chunks)
            self.assertTrue(all(chunk.skill_id.startswith("support.") for chunk in context.chunks))

    def test_resolver_limits_uploaded_skills_to_matching_user_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp)
            self._write(
                skills_root / "support" / "persona.md",
                """---
title: Support Persona
type: persona
summary: Keep support replies concrete and operational.
tags: [support, persona]
mode: always_on
priority: 100
---

# Support Persona

Be concrete and operational.
""",
            )
            self._write(
                skills_root / "uploads" / "browser-user" / "refund-policy.md",
                """---
title: Refund Policy Upload
type: knowledge
summary: User-uploaded refund rules and timelines.
tags: [uploaded, refund]
triggers: [refund, reimbursement]
mode: auto
priority: 70
---

# Refund Policy

Refunds are available within 30 days for annual plans.
""",
            )

            resolver = SkillResolver(SkillStore(skills_root))
            matching_context = resolver.resolve(
                query="What is the refund timeline for annual plans?",
                user_id="browser-user",
                skill_scopes=("support",),
                always_on_skill_ids=(),
            )
            other_user_context = resolver.resolve(
                query="What is the refund timeline for annual plans?",
                user_id="another-user",
                skill_scopes=("support",),
                always_on_skill_ids=(),
            )

            self.assertEqual([skill.id for skill in matching_context.always_on_skills], ["support.persona"])
            self.assertEqual(
                [skill.id for skill in matching_context.selected_skills],
                ["uploads.browser-user.refund-policy"],
            )
            self.assertTrue(
                any(chunk.skill_id == "uploads.browser-user.refund-policy" for chunk in matching_context.chunks)
            )
            self.assertEqual([skill.id for skill in other_user_context.always_on_skills], ["support.persona"])
            self.assertEqual(other_user_context.selected_skills, ())
            self.assertTrue(all(chunk.skill_id == "support.persona" for chunk in other_user_context.chunks))

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
