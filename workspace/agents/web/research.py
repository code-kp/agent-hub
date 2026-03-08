"""
Tests:
- tests/workspace/agents/web/test_research.py
"""

from __future__ import annotations

from core.contracts.agent import (
    OrchestratedAgentModule,
    register_orchestrated_agent_class,
)
from core.contracts.execution import ExecutionConfig
from workspace.agents.web.hooks import WebCitationHooks


@register_orchestrated_agent_class
class WebResearch(OrchestratedAgentModule):
    name = "Web Research"
    description = "Plans, researches, verifies, and answers using public web sources."
    system_prompt = (
        "Answer factual or current questions with enough detail to fully address the user's request. "
        "Prefer reliable public sources, verify important claims before concluding, and use inline "
        "numeric citations like [1] when the answer relies on web evidence."
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
