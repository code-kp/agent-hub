from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Tuple

from core.memory.context import MemoryMessage, MemorySnapshot


@dataclass
class ThreadMemoryRecord:
    summary: str = ""
    recent_turns: list[MemoryMessage] = field(default_factory=list)
    turn_count: int = 0

    def snapshot(self) -> MemorySnapshot:
        return MemorySnapshot(
            summary=self.summary,
            recent_turns=tuple(self.recent_turns),
        )


class MemoryStore:
    def __init__(self) -> None:
        self._records: Dict[Tuple[str, str], ThreadMemoryRecord] = {}

    def get_or_create(self, *, user_id: str, session_id: str) -> ThreadMemoryRecord:
        key = (user_id, session_id)
        record = self._records.get(key)
        if record is None:
            record = ThreadMemoryRecord()
            self._records[key] = record
        return record

    def seed_recent_turns(
        self,
        *,
        user_id: str,
        session_id: str,
        recent_turns: Iterable[MemoryMessage],
    ) -> ThreadMemoryRecord:
        record = self.get_or_create(user_id=user_id, session_id=session_id)
        if not record.summary.strip() and not record.recent_turns:
            record.recent_turns = list(recent_turns)
        return record
