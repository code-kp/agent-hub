from __future__ import annotations

from typing import Mapping, Sequence

import core.contracts.memory as contracts_memory
from core.memory.context import MemoryMessage, MemorySnapshot, normalize_memory_messages
from core.memory.store import MemoryStore
from core.memory.summarizer import MemorySummarizer


class MemoryManager:
    def __init__(
        self,
        *,
        agent_id: str,
        model_name: str,
        config: contracts_memory.MemoryConfig,
    ) -> None:
        self.agent_id = agent_id
        self.model_name = model_name
        self.config = config
        self.store = MemoryStore()
        self.summarizer = MemorySummarizer(agent_id=agent_id, model_name=model_name)

    async def prepare_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        seed_history: Sequence[Mapping[str, str]] | None = None,
    ) -> MemorySnapshot:
        if not self.config.enabled:
            return MemorySnapshot()

        seeded_turns = normalize_memory_messages(
            seed_history,
            limit=self.config.max_seed_messages,
        )
        record = self.store.seed_recent_turns(
            user_id=user_id,
            session_id=session_id,
            recent_turns=seeded_turns,
        )
        return record.snapshot()

    async def record_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_message: str,
    ) -> MemorySnapshot:
        if not self.config.enabled:
            return MemorySnapshot()

        record = self.store.get_or_create(user_id=user_id, session_id=session_id)
        appended = normalize_memory_messages(
            [
                {"role": "user", "text": user_message},
                {"role": "assistant", "text": assistant_message},
            ],
            limit=2,
            max_chars=480,
        )
        record.recent_turns.extend(appended)
        record.turn_count += 1

        preserve_recent_messages = max(2, self.config.preserve_recent_turns * 2)
        summarize_after_messages = max(
            preserve_recent_messages + 2, self.config.summarize_after_turns * 2
        )
        if len(record.recent_turns) >= summarize_after_messages:
            older_turns = record.recent_turns[:-preserve_recent_messages]
            record.recent_turns = record.recent_turns[-preserve_recent_messages:]
            record.summary = await self.summarizer.summarize(
                existing_summary=record.summary,
                older_turns=older_turns,
                max_summary_chars=self.config.max_summary_chars,
            )

        return record.snapshot()
