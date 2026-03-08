import unittest
from unittest.mock import AsyncMock

from core.contracts.memory import DISABLED_MEMORY_CONFIG, MemoryConfig
from core.memory.context import MemorySnapshot
from core.memory.manager import MemoryManager


class MemoryManagerTest(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_turn_seeds_from_request_history(self) -> None:
        manager = MemoryManager(
            agent_id="general",
            model_name="gemini-test",
            config=MemoryConfig(
                enabled=True, preserve_recent_turns=2, summarize_after_turns=3
            ),
        )

        snapshot = await manager.prepare_turn(
            user_id="user-1",
            session_id="session-1",
            seed_history=[
                {"role": "user", "text": "I need help with a failed checkout."},
                {"role": "assistant", "text": "What error did you see?"},
            ],
        )

        self.assertEqual(len(snapshot.recent_turns), 2)
        self.assertEqual(snapshot.recent_turns[0].role, "user")

    async def test_record_turn_rolls_older_messages_into_summary(self) -> None:
        manager = MemoryManager(
            agent_id="general",
            model_name="gemini-test",
            config=MemoryConfig(
                enabled=True, preserve_recent_turns=2, summarize_after_turns=3
            ),
        )
        manager.summarizer.summarize = AsyncMock(
            return_value="User is fixing a failed checkout and needs next steps."
        )

        await manager.prepare_turn(
            user_id="user-1",
            session_id="session-1",
            seed_history=[
                {"role": "user", "text": "My checkout failed."},
                {"role": "assistant", "text": "What payment method were you using?"},
                {"role": "user", "text": "Visa."},
                {
                    "role": "assistant",
                    "text": "Try the card again after confirming the address.",
                },
            ],
        )
        snapshot = await manager.record_turn(
            user_id="user-1",
            session_id="session-1",
            user_message="It still failed.",
            assistant_message="Use a different card and check the issuer decline details.",
        )

        self.assertIn("failed checkout", snapshot.summary)
        self.assertLessEqual(len(snapshot.recent_turns), 4)
        manager.summarizer.summarize.assert_awaited_once()

    async def test_disabled_memory_is_empty(self) -> None:
        manager = MemoryManager(
            agent_id="general",
            model_name="gemini-test",
            config=DISABLED_MEMORY_CONFIG,
        )

        prepared = await manager.prepare_turn(
            user_id="user-1",
            session_id="session-1",
            seed_history=[{"role": "user", "text": "hello"}],
        )
        recorded = await manager.record_turn(
            user_id="user-1",
            session_id="session-1",
            user_message="hello",
            assistant_message="world",
        )

        self.assertEqual(prepared, MemorySnapshot())
        self.assertEqual(recorded, MemorySnapshot())


if __name__ == "__main__":
    unittest.main()
