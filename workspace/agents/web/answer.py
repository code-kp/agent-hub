from __future__ import annotations

from core.contracts.agent import AgentModule, register_agent_class


@register_agent_class
class WebAnswer(AgentModule):
    name = "Web Answer"
    description = "Searches the internet and answers with a crisp direct summary."
    system_prompt = (
        "Use the web tools to answer factual or current questions. Search first, then fetch at most "
        "two pages only if the snippets are not enough. Answer directly in 1-4 sentences. "
        "Do not add preamble, bullet lists, or explain the process unless the user asks. "
        "Prefer the clearest credible source and keep the answer tight."
    )
    tools = (
        "get_current_utc_time",
        "search_web",
        "fetch_web_page",
    )
