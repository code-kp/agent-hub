import inspect
import unittest

from core.contracts.tools import (
    ToolDefinition,
    ToolModule,
    ensure_tools,
    register_tool_class,
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

        self.assertEqual(
            inspect.signature(callable_tool), inspect.signature(definition.handler)
        )
        self.assertIn(callable_tool.__annotations__.get("query"), ("str", str))
        self.assertIn(callable_tool.__annotations__.get("return"), ("dict", dict))


if __name__ == "__main__":
    unittest.main()
