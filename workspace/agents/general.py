from __future__ import annotations

from core.contracts.agent import AgentModule, register_agent_class


@register_agent_class
class GeneralAssistant(AgentModule):
    name = "General Assistant"
    description = "General-purpose product and onboarding assistant."
    system_prompt = (
        "Answer clearly and concisely. Use skills when relevant, avoid inventing facts, "
        "and call tools for data access when needed."
    )
    tools = (
        "get_current_utc_time",
        "search_skills",
        "list_skill_files",
        "read_skill_file",
    )
    skill_scopes = ("general",)
    always_on_skills = ("general.persona",)
