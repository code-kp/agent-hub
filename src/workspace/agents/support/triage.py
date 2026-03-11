from __future__ import annotations

from core.contracts.agent import AgentModule, register_agent_class


@register_agent_class
class SupportTriage(AgentModule):
    name = "Support Triage"
    description = "Support-focused agent for debugging and next-step guidance."
    system_prompt = (
        "When troubleshooting, separate confirmed facts from assumptions, suggest concrete "
        "next checks, and keep answers operational."
    )
    tools = ("get_current_utc_time",)
    behavior = ("support.persona", "support.policy")
    knowledge = ("support.triage", "general.product")
