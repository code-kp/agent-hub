from __future__ import annotations

from core.contracts.agent import AgentModule, register_agent_class
from core.contracts.execution import ExecutionConfig


@register_agent_class
class Coder(AgentModule):
    name = "Coder"
    description = "best coder in the world."
    system_prompt = (
        "You are the Coder. best coder in the world. Give clear, moderately detailed "
        "answers that stay focused on the user's goal. Use skills when relevant, avoid "
        "inventing facts, and call tools only when they add material value. If the answer "
        "would require unavailable data, say what is missing instead of guessing."
    )
    tools = ()
    behavior = (
        "users.persona",
    )
    knowledge = (
        "users.technology.coder",
    )
    runtime_mode = "orchestrated"
    execution = ExecutionConfig(max_tool_calls=6)
