from __future__ import annotations

from typing import Any


HookState = dict[str, Any]


class AgentHooks:
    """Optional agent-owned lifecycle hooks invoked by the runtime."""

    def create_turn_state(
        self,
        *,
        agent_id: str,
        user_id: str,
        session_id: str,
        message: str,
    ) -> HookState:
        return {}

    def build_prompt_guidance(
        self,
        *,
        phase: str,
        state: HookState,
    ) -> str:
        return ""

    def on_tool_response(
        self,
        *,
        state: HookState,
        tool_name: str,
        payload: Any,
    ) -> None:
        return None

    def finalize_response(
        self,
        *,
        text: str,
        state: HookState,
    ) -> str:
        return text


DEFAULT_AGENT_HOOKS = AgentHooks()


def ensure_agent_hooks(hooks: AgentHooks | None) -> AgentHooks:
    if hooks is None:
        return DEFAULT_AGENT_HOOKS
    if not isinstance(hooks, AgentHooks):
        raise TypeError("Agent hooks must be an AgentHooks instance.")
    return hooks
