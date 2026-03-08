import unittest

from google.genai import types

import core.execution.direct.prompts as direct_prompts
from core.memory.context import MemoryMessage, MemorySnapshot
from core.skills.resolver import ResolvedSkillContext


class DirectPromptRuntimeContextTest(unittest.TestCase):
    def test_apply_runtime_context_includes_recent_history(self) -> None:
        llm_request = types.GenerateContentConfig()
        wrapper = type("Request", (), {"config": llm_request})()

        direct_prompts.apply_runtime_context(
            wrapper,
            ResolvedSkillContext(),
            conversation_history=[
                {"role": "user", "text": "My order failed yesterday."},
                {
                    "role": "assistant",
                    "text": "Which order number are you asking about?",
                },
            ],
        )

        system_instruction = wrapper.config.system_instruction
        self.assertIsNotNone(system_instruction)
        self.assertIn("Recent conversation history:", system_instruction.parts[0].text)
        self.assertIn(
            "user: My order failed yesterday.", system_instruction.parts[0].text
        )

    def test_apply_runtime_context_prefers_compact_memory_when_available(self) -> None:
        llm_request = types.GenerateContentConfig()
        wrapper = type("Request", (), {"config": llm_request})()

        direct_prompts.apply_runtime_context(
            wrapper,
            ResolvedSkillContext(),
            conversation_history=[
                {"role": "user", "text": "Old raw turn."},
            ],
            memory_snapshot=MemorySnapshot(
                summary="User is troubleshooting a failed checkout and wants concrete next steps.",
                recent_turns=(
                    MemoryMessage(role="assistant", text="Asked for the order number."),
                ),
            ),
        )

        system_instruction = wrapper.config.system_instruction
        self.assertIsNotNone(system_instruction)
        self.assertIn("Conversation memory:", system_instruction.parts[0].text)
        self.assertNotIn(
            "Recent conversation history:", system_instruction.parts[0].text
        )


if __name__ == "__main__":
    unittest.main()
