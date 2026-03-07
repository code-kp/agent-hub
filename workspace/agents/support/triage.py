from __future__ import annotations

from core.interfaces.agent import AgentModule, register_agent_class


@register_agent_class
class SupportTriage(AgentModule):
    name = "Support Triage"
    description = "Support-focused agent for debugging and next-step guidance."
    system_prompt = (
        "When troubleshooting, separate confirmed facts from assumptions, suggest concrete "
        "next checks, and keep answers operational."
    )
    tools = (
        "get_current_utc_time",
        "search_skills",
        "list_skill_files",
        "read_skill_file",
    )
    skills_dir = "support"
