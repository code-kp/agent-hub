from __future__ import annotations

from core.contracts.agent import AgentModule, register_agent_class
from core.contracts.execution import ExecutionConfig


@register_agent_class
class PythonCoder(AgentModule):
    name = "Python Coder"
    description = "Python Expert."
    system_prompt = (
        "You are the Python Coder. Focuses only on Python Language. Give clear, "
        "moderately detailed answers that stay focused on the user's goal. Use skills "
        "when relevant, avoid inventing facts, and call tools only when they add material "
        "value. If the answer would require unavailable data, say what is missing instead "
        "of guessing."
    )
    tools = ()
    behavior = (
        "users.persona",
    )
    knowledge = (
        "users.technology.python_coder",
    )
    runtime_mode = "orchestrated"
    execution = ExecutionConfig(max_tool_calls=6)
