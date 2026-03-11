"""
Tests:
- tests/workspace/agents/web/test_answer.py
"""

from __future__ import annotations

from core.contracts.agent import AgentModule, register_agent_class
from core.contracts.execution import ExecutionConfig
from workspace.agents.web.hooks import WebCitationHooks


@register_agent_class
class WebAnswer(AgentModule):
    name = "Web Answer"
    description = "Searches the internet and answers with a sourced, complete summary."
    system_prompt = (
        "Use the web tools to answer factual or current questions. Search first, then fetch at most "
        "two pages only if the snippets are not enough. Give a clear, moderately detailed answer that "
        "fully addresses the question, usually in two or three short paragraphs unless the user asks "
        "for something shorter. Prefer the clearest credible sources, synthesize what they say, and "
        "do not explain the process unless the user asks. When the answer relies on web tools, add "
        "inline citations immediately after the supported sentence using markdown links with numeric "
        "labels like [1](https://example.com). Reuse the same citation number when citing the same "
        "URL again, and do not add a separate Sources section at the end."
    )
    tools = (
        "get_current_utc_time",
        "search_web",
        "fetch_web_page",
    )
    execution = ExecutionConfig(
        max_tool_calls=8,
        max_calls_per_tool=3,
        max_replans=3,
        max_verification_rounds=2,
    )
    hooks = WebCitationHooks()
