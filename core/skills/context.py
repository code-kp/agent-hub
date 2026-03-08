from __future__ import annotations

import contextvars
from typing import Optional

from core.skills.store import SkillStore


_current_skill_store: contextvars.ContextVar[Optional[SkillStore]] = (
    contextvars.ContextVar(
        "current_skill_store",
        default=None,
    )
)


def bind_skill_store(store: SkillStore) -> contextvars.Token:
    return _current_skill_store.set(store)


def reset_skill_store(token: contextvars.Token) -> None:
    _current_skill_store.reset(token)


def current_skill_store() -> SkillStore:
    store = _current_skill_store.get()
    if store is None:
        raise RuntimeError(
            "No active skill store is bound to the current runtime context."
        )
    return store
