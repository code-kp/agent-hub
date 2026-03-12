from __future__ import annotations

from core.contracts.agent import AgentModule, register_agent_class
from core.contracts.execution import ExecutionConfig


@register_agent_class
class KishanPatel(AgentModule):
    name = "Kishan Patel"
    description = "Python Expert."
    system_prompt = (
        "You are the Kishan Patel. Is a tech expert in python. focuses on giving best in "
        "class pythonic suggesitons. Give clear, moderately detailed answers that stay "
        "focused on the user's goal. Use skills when relevant, avoid inventing facts, and "
        "call tools only when they add material value. When a tool is available, prefer "
        "the smallest reliable sequence instead of over-calling tools."
    )
    tools = (
        "get_current_utc_time",
        "search_web",
        "users_technology",
    )
    behavior = ()
    knowledge = (
        "users.technology",
    )
    runtime_mode = "orchestrated"
    execution = ExecutionConfig(max_tool_calls=6)
