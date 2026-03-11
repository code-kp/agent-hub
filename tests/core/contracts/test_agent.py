import unittest

from core.contracts.agent import AgentModule, agent_from_class, define_agent
from core.contracts.execution import ExecutionConfig
from core.contracts.memory import DISABLED_MEMORY_CONFIG
from core.contracts.tools import (
    ToolDefinition,
    ToolModule,
    ensure_tools,
    register_core_toolset,
    register_tool_class,
    tool_reference_name,
)
from core.registry import Register


@register_tool_class
class ExplicitPingTool(ToolModule):
    name = "explicit_ping"
    description = "Explicit ping tool."

    def run(self) -> dict:
        return {"ok": True}


@register_tool_class
class CoreSearchTool(ToolModule):
    name = "core_search"
    description = "Framework-provided search tool."

    def run(self, query: str) -> dict:
        return {"query": query}


register_core_toolset("test_core", (CoreSearchTool,), overwrite=True)


class AgentContractsTest(unittest.TestCase):
    def tearDown(self) -> None:
        Register.clear(ToolDefinition)
        register_tool_class(ExplicitPingTool)
        register_tool_class(CoreSearchTool)
        register_core_toolset("test_core", (CoreSearchTool,), overwrite=True)

    def test_agent_includes_core_tools_without_explicit_listing(self) -> None:
        agent = define_agent(
            name="Core Tool Agent",
            description="Uses core tools implicitly.",
            system_prompt="Answer clearly.",
            tools=("explicit_ping",),
            core_toolsets=("test_core",),
        )

        self.assertEqual(
            [tool_reference_name(tool) for tool in agent.tools],
            ["core_search", "explicit_ping"],
        )
        self.assertEqual(
            [tool.name for tool in ensure_tools(agent.tools)],
            ["core_search", "explicit_ping"],
        )

    def test_agent_can_disable_core_tools(self) -> None:
        agent = define_agent(
            name="Explicit Only Agent",
            description="Uses explicit tools only.",
            system_prompt="Answer clearly.",
            tools=("explicit_ping",),
            include_core_tools=False,
            core_toolsets=("test_core",),
        )

        self.assertEqual(
            [tool_reference_name(tool) for tool in agent.tools],
            ["explicit_ping"],
        )

    def test_agent_class_can_default_to_orchestrated_runtime_mode(self) -> None:
        class OrchestratedExample(AgentModule):
            name = "Orchestrated Example"
            description = "Runs the explicit controller loop."
            system_prompt = "Answer clearly."
            runtime_mode = "orchestrated"
            tools = ("explicit_ping",)
            execution = ExecutionConfig(max_tool_calls=6)

        definition = agent_from_class(OrchestratedExample)

        self.assertEqual(definition.runtime_mode, "orchestrated")
        self.assertTrue(definition.orchestration_configured)

    def test_direct_agent_without_execution_does_not_opt_into_orchestration(
        self,
    ) -> None:
        agent = define_agent(
            name="Direct Only Agent",
            description="Uses default direct runtime settings.",
            system_prompt="Answer clearly.",
            tools=("explicit_ping",),
        )

        self.assertFalse(agent.orchestration_configured)

    def test_explicit_execution_config_enables_orchestration_capability(self) -> None:
        agent = define_agent(
            name="Execution Configured Agent",
            description="Opts into orchestrated runtime support.",
            system_prompt="Answer clearly.",
            tools=("explicit_ping",),
            execution=ExecutionConfig(max_tool_calls=6),
        )

        self.assertTrue(agent.orchestration_configured)

    def test_orchestrated_runtime_requires_execution_config(self) -> None:
        with self.assertRaises(ValueError):
            define_agent(
                name="Invalid Orchestrated Agent",
                description="Missing explicit execution config.",
                system_prompt="Answer clearly.",
                tools=("explicit_ping",),
                runtime_mode="orchestrated",
            )

    def test_agent_can_disable_memory(self) -> None:
        agent = define_agent(
            name="Stateless Agent",
            description="Does not keep rolling memory.",
            system_prompt="Answer clearly.",
            tools=("explicit_ping",),
            memory=DISABLED_MEMORY_CONFIG,
        )

        self.assertFalse(agent.memory.enabled)

    def test_agent_can_define_behavior_and_knowledge_skills(self) -> None:
        agent = define_agent(
            name="Skill Agent",
            description="Uses simplified skill lists.",
            system_prompt="Answer clearly.",
            tools=("explicit_ping",),
            behavior=("support/persona",),
            knowledge=("support/triage", "general.product"),
        )

        self.assertEqual(agent.behavior, ("support.persona",))
        self.assertEqual(agent.knowledge, ("support.triage", "general.product"))

    def test_class_surface_supports_behavior_and_knowledge(self) -> None:
        class AliasAgent(AgentModule):
            name = "Alias Example"
            description = "Uses shorter skill aliases."
            system_prompt = "Answer clearly."
            tools = ("explicit_ping",)
            behavior = ("support.persona",)
            knowledge = ("support.triage",)

        definition = agent_from_class(AliasAgent)

        self.assertEqual(definition.behavior, ("support.persona",))
        self.assertEqual(definition.knowledge, ("support.triage",))


if __name__ == "__main__":
    unittest.main()
