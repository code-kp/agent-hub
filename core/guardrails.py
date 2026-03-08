"""
Tests:
- tests/core/test_guardrails.py
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque

from core.contracts.execution import ExecutionConfig


@dataclass(frozen=True)
class ToolCallRecord:
    tool_name: str
    args_key: str


@dataclass
class ToolLoopState:
    total_calls: int = 0
    calls_by_tool: dict[str, int] = field(default_factory=dict)
    recent_calls: Deque[ToolCallRecord] = field(default_factory=deque)


class ToolLoopGuardrails:
    def __init__(self, config: ExecutionConfig) -> None:
        self.config = config
        self.state = ToolLoopState()

    def authorize(self, tool_name: str, tool_args: dict[str, Any]) -> str | None:
        if self.state.total_calls >= self.config.max_tool_calls:
            return (
                "The tool-call budget for this turn has been reached. "
                "Use the information already gathered or answer without another tool call."
            )

        calls_for_tool = self.state.calls_by_tool.get(tool_name, 0)
        if calls_for_tool >= self.config.max_calls_per_tool:
            return (
                "This tool has already been used the allowed number of times for this turn. "
                "Choose another tool or answer with the available evidence."
            )

        consecutive_calls = self._consecutive_calls_for_tool(tool_name)
        if consecutive_calls >= self.config.max_consecutive_calls_per_tool:
            return (
                "The same tool has been used repeatedly without enough progress. "
                "Change approach instead of calling it again immediately."
            )

        args_key = _normalize_tool_args(tool_args)
        if self.config.block_duplicate_call_arguments and self._seen_duplicate_call(
            tool_name, args_key
        ):
            return (
                "This exact tool call was already tried for this turn. "
                "Reuse the earlier result or change the inputs."
            )

        self._record_call(tool_name, args_key)
        return None

    def _record_call(self, tool_name: str, args_key: str) -> None:
        self.state.total_calls += 1
        self.state.calls_by_tool[tool_name] = (
            self.state.calls_by_tool.get(tool_name, 0) + 1
        )
        self.state.recent_calls.append(
            ToolCallRecord(tool_name=tool_name, args_key=args_key)
        )
        while len(self.state.recent_calls) > self.config.duplicate_call_window:
            self.state.recent_calls.popleft()

    def _consecutive_calls_for_tool(self, tool_name: str) -> int:
        count = 0
        for item in reversed(self.state.recent_calls):
            if item.tool_name != tool_name:
                break
            count += 1
        return count

    def _seen_duplicate_call(self, tool_name: str, args_key: str) -> bool:
        return any(
            item.tool_name == tool_name and item.args_key == args_key
            for item in self.state.recent_calls
        )


def _normalize_tool_args(tool_args: dict[str, Any]) -> str:
    if not tool_args:
        return "{}"
    return json.dumps(tool_args, sort_keys=True, default=str)
