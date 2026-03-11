from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class MemoryMessage:
    role: str
    text: str


@dataclass(frozen=True)
class MemorySnapshot:
    summary: str = ""
    recent_turns: tuple[MemoryMessage, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.summary.strip() and not self.recent_turns


def normalize_memory_messages(
    messages: Sequence[Mapping[str, Any]] | None,
    *,
    limit: int = 8,
    max_chars: int = 320,
) -> list[MemoryMessage]:
    normalized: list[MemoryMessage] = []
    for item in list(messages or [])[-limit:]:
        role = str(item.get("role") or "").strip().lower()
        text = " ".join(str(item.get("text") or "").split()).strip()
        if role not in {"user", "assistant"} or not text:
            continue
        if len(text) > max_chars:
            text = "{value}...".format(value=text[: max_chars - 3].rstrip())
        normalized.append(MemoryMessage(role=role, text=text))
    return normalized


def format_memory_context(snapshot: MemorySnapshot) -> str:
    if snapshot.is_empty:
        return ""

    sections: list[str] = [
        "Conversation memory:",
        "Use this compact memory to resolve follow-up references and preserve earlier decisions without replaying the full transcript.",
    ]
    if snapshot.summary.strip():
        sections.extend(
            [
                "Rolling summary:",
                snapshot.summary.strip(),
            ]
        )
    if snapshot.recent_turns:
        sections.append("Recent turns:")
        for item in snapshot.recent_turns:
            sections.append("{role}: {text}".format(role=item.role, text=item.text))
    return "\n".join(sections)
