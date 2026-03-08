import contextvars
import inspect
import unittest

from core.contracts.tools import (
    ToolDefinition,
    ToolModule,
    ensure_tools,
    register_tool_class,
)
from core.registry import Register
import core.execution.shared.tooling as runtime_tooling


@register_tool_class
class CoreSearchTool(ToolModule):
    name = "core_search"
    description = "Framework-provided search tool."

    def run(self, query: str) -> dict:
        return {"query": query}


class SharedToolingTest(unittest.TestCase):
    def tearDown(self) -> None:
        Register.clear(ToolDefinition)
        register_tool_class(CoreSearchTool)

    def test_guarded_tool_preserves_parameter_annotations(self) -> None:
        definition = ensure_tools((CoreSearchTool,))[0]
        callable_tool = runtime_tooling.build_guarded_tool_callable(
            definition,
            agent_id="test-agent",
            tool_guardrails=contextvars.ContextVar(
                "tool_guardrails_test", default=None
            ),
        )

        self.assertEqual(
            inspect.signature(callable_tool), inspect.signature(definition.handler)
        )
        self.assertIn(callable_tool.__annotations__.get("query"), ("str", str))
        self.assertIn(callable_tool.__annotations__.get("return"), ("dict", dict))


if __name__ == "__main__":
    unittest.main()
