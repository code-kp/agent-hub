from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionConfig:
    """
    Runtime execution decisions that stay deterministic while tool planning remains model-driven.

    The framework should decide limits and safety constraints, not user-intent routing.
    """

    max_tool_calls: int = 8
    max_calls_per_tool: int = 3
    max_consecutive_calls_per_tool: int = 2
    block_duplicate_call_arguments: bool = True
    duplicate_call_window: int = 4
    max_replans: int = 3
    max_verification_rounds: int = 2
    include_tool_catalog: bool = True

    def __post_init__(self) -> None:
        for field_name in (
            "max_tool_calls",
            "max_calls_per_tool",
            "max_consecutive_calls_per_tool",
            "duplicate_call_window",
            "max_replans",
            "max_verification_rounds",
        ):
            value = int(getattr(self, field_name))
            if value <= 0:
                raise ValueError("{field_name} must be greater than zero.".format(field_name=field_name))


DEFAULT_EXECUTION_CONFIG = ExecutionConfig()


def ensure_execution_config(value: ExecutionConfig | None) -> ExecutionConfig:
    if value is None:
        return DEFAULT_EXECUTION_CONFIG
    if not isinstance(value, ExecutionConfig):
        raise TypeError("execution must be an ExecutionConfig instance.")
    return value
