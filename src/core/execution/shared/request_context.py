from __future__ import annotations

import contextvars


_conversation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "conversation_id",
    default="",
)


def bind_conversation_id(conversation_id: str | None) -> contextvars.Token:
    normalized = str(conversation_id or "").strip()
    return _conversation_id.set(normalized)


def current_conversation_id() -> str | None:
    normalized = str(_conversation_id.get() or "").strip()
    return normalized or None


def reset_conversation_id(token: contextvars.Token) -> None:
    _conversation_id.reset(token)
