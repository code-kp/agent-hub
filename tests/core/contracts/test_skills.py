import unittest
from pathlib import Path

from core.contracts.skills import SkillDefinition, ensure_skill_ids


class SkillContractsTest(unittest.TestCase):
    def test_skill_id_helpers_normalize_and_dedupe_values(self) -> None:
        self.assertEqual(
            ensure_skill_ids(("support/triage", "support.triage")),
            ("support.triage",),
        )

    def test_skill_definition_can_record_behavior_class(self) -> None:
        skill = SkillDefinition(
            id="support.persona",
            source="behavior/support/persona.md",
            path=Path("behavior/support/persona.md"),
            title="Support Persona",
            summary="Keep replies concrete.",
            skill_class="behavior",
        )

        self.assertTrue(skill.is_behavior)
        self.assertFalse(skill.is_knowledge)


if __name__ == "__main__":
    unittest.main()
