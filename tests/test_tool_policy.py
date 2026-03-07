import unittest
from pathlib import Path

from core.contracts.skills import SkillDefinition
from core.contracts.tools import ToolDefinition
from core.skills.resolver import ResolvedSkillContext
from core.policies.tool_policy import plan_tool_execution


def _tool(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"{name} description",
        handler=lambda **kwargs: kwargs,
    )


def _skill(skill_id: str) -> SkillDefinition:
    return SkillDefinition(
        id=skill_id,
        source=f"{skill_id.replace('.', '/')}.md",
        path=Path(f"{skill_id.replace('.', '/')}.md"),
        title=skill_id,
        skill_type="knowledge",
        summary="summary",
    )


class ToolPolicyTest(unittest.TestCase):
    def test_temporal_public_query_uses_time_then_web(self) -> None:
        plan = plan_tool_execution(
            query="latest OpenAI news",
            available_tools=(_tool("get_current_utc_time"), _tool("search_web")),
            resolved_context=ResolvedSkillContext(),
        )

        self.assertEqual(
            [item.tool_name for item in plan.preflight_calls],
            ["get_current_utc_time", "search_web"],
        )

    def test_exact_time_query_only_uses_time_tool(self) -> None:
        plan = plan_tool_execution(
            query="what time is it in UTC right now?",
            available_tools=(_tool("get_current_utc_time"), _tool("search_web")),
            resolved_context=ResolvedSkillContext(),
        )

        self.assertEqual(
            [item.tool_name for item in plan.preflight_calls],
            ["get_current_utc_time"],
        )

    def test_internal_guidance_query_does_not_force_web_search_when_skills_exist(self) -> None:
        context = ResolvedSkillContext(
            selected_skills=(_skill("support.policy"),),
        )
        plan = plan_tool_execution(
            query="what is the current refund policy for annual plans?",
            available_tools=(_tool("get_current_utc_time"), _tool("search_web")),
            resolved_context=context,
        )

        self.assertEqual(
            [item.tool_name for item in plan.preflight_calls],
            ["get_current_utc_time"],
        )


if __name__ == "__main__":
    unittest.main()
