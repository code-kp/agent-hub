import contextvars
import unittest
import inspect

from core.contracts.agent import OrchestratedAgentModule, agent_from_class, define_agent
from core.contracts.execution import ExecutionConfig
from core.contracts.tools import (
    ToolModule,
    ToolDefinition,
    ensure_tools,
    register_core_toolset,
    register_tool_class,
    tool_reference_name,
)
from core.registry import Register
import core.execution.shared.tooling as runtime_tooling


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


class ToolContractsTest(unittest.TestCase):
    def tearDown(self) -> None:
        Register.clear(ToolDefinition)
        register_tool_class(ExplicitPingTool)
        register_tool_class(CoreSearchTool)

    def test_tool_class_registers_as_tool_definition(self) -> None:
        definition = ensure_tools((ExplicitPingTool,))[0]

        self.assertEqual(definition.name, "explicit_ping")
        self.assertEqual(definition.description, "Explicit ping tool.")

    def test_wrapped_tool_preserves_parameter_annotations(self) -> None:
        definition = ensure_tools((CoreSearchTool,))[0]
        callable_tool = definition.build_callable()

        self.assertEqual(inspect.signature(callable_tool), inspect.signature(definition.handler))
        self.assertIn(callable_tool.__annotations__.get("query"), ("str", str))
        self.assertIn(callable_tool.__annotations__.get("return"), ("dict", dict))

    def test_guarded_tool_preserves_parameter_annotations(self) -> None:
        definition = ensure_tools((CoreSearchTool,))[0]
        callable_tool = runtime_tooling.build_guarded_tool_callable(
            definition,
            agent_id="test-agent",
            tool_guardrails=contextvars.ContextVar("tool_guardrails_test", default=None),
        )

        self.assertEqual(inspect.signature(callable_tool), inspect.signature(definition.handler))
        self.assertIn(callable_tool.__annotations__.get("query"), ("str", str))
        self.assertIn(callable_tool.__annotations__.get("return"), ("dict", dict))

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

    def test_agent_accepts_execution_guardrails(self) -> None:
        agent = define_agent(
            name="Guardrailed Agent",
            description="Uses explicit limits.",
            system_prompt="Answer clearly.",
            tools=("explicit_ping",),
            execution=ExecutionConfig(max_tool_calls=4, max_calls_per_tool=2, max_replans=2),
        )

        self.assertEqual(agent.execution.max_tool_calls, 4)
        self.assertEqual(agent.execution.max_calls_per_tool, 2)
        self.assertEqual(agent.execution.max_replans, 2)

    def test_orchestrated_agent_class_sets_orchestrated_runtime_mode(self) -> None:
        class OrchestratedExample(OrchestratedAgentModule):
            name = "Orchestrated Example"
            description = "Runs the explicit controller loop."
            system_prompt = "Answer clearly."
            tools = ("explicit_ping",)

        definition = agent_from_class(OrchestratedExample)

        self.assertEqual(definition.runtime_mode, "orchestrated")


if __name__ == "__main__":
    unittest.main()
