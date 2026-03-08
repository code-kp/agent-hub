"""
Tests:
- tests/core/contracts/test_memory.py
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryConfig:
    """
    Controls whether the framework maintains a compact conversation memory for an agent.

    When enabled, the runtime keeps a rolling summary plus a small set of recent turns,
    which reduces prompt growth compared with replaying the full transcript.
    """

    enabled: bool = True
    preserve_recent_turns: int = 4
    summarize_after_turns: int = 6
    max_seed_messages: int = 8
    max_summary_chars: int = 1200

    def __post_init__(self) -> None:
        for field_name in (
            "preserve_recent_turns",
            "summarize_after_turns",
            "max_seed_messages",
            "max_summary_chars",
        ):
            value = int(getattr(self, field_name))
            if value <= 0:
                raise ValueError(
                    "{field_name} must be greater than zero.".format(
                        field_name=field_name
                    )
                )


DEFAULT_MEMORY_CONFIG = MemoryConfig()
DISABLED_MEMORY_CONFIG = MemoryConfig(enabled=False)


def ensure_memory_config(value: MemoryConfig | None) -> MemoryConfig:
    if value is None:
        return DEFAULT_MEMORY_CONFIG
    if not isinstance(value, MemoryConfig):
        raise TypeError("memory must be a MemoryConfig instance.")
    return value
