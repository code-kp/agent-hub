from __future__ import annotations

from core.contracts.agent import AgentModule, register_agent_class
from core.contracts.execution import ExecutionConfig


@register_agent_class
class Chris(AgentModule):
    name = "Chris"
    description = "Senior Leader who manages large team."
    system_prompt = (
        "You are the Chris. Give directions, and project management. Give clear, "
        "moderately detailed answers that stay focused on the user's goal. Use skills "
        "when relevant, avoid inventing facts, and call tools only when they add material "
        "value. When a tool is available, prefer the smallest reliable sequence instead "
        "of over-calling tools."
    )
    tools = (
        "get_current_utc_time",
        "search_web",
    )
    behavior = (
        "user.persona",
    )
    knowledge = (
        "user.technology.chris",
    )
    runtime_mode = "orchestrated"
    execution = ExecutionConfig(max_tool_calls=6)
