from __future__ import annotations

from core.contracts.agent import AgentModule, register_agent_class


@register_agent_class
class JavaExpert(AgentModule):
    name = "Java Expert"
    description = "Java Expert."
    system_prompt = (
        "You are the Java Expert. Gives java suggestions. Give clear, moderately detailed "
        "answers that stay focused on the user's goal. Use skills when relevant, avoid "
        "inventing facts, and call tools only when they add material value. If the answer "
        "would require unavailable data, say what is missing instead of guessing."
    )
    tools = ()
    behavior = (
        "users.persona",
    )
    knowledge = (
        "users.java_expert",
    )
    runtime_mode = "direct"
