import tempfile
import unittest
from pathlib import Path

from core.discovery import DiscoveryService
from core.interfaces.tools import ToolDefinition
from core.registry import Register


class DiscoveryCollaborationTest(unittest.TestCase):
    def setUp(self) -> None:
        Register.clear()

    def tearDown(self) -> None:
        Register.clear()

    def test_discovers_agents_and_tools_from_simplified_workspace_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "sandboxspace"
            self._write(workspace_root / "__init__.py", "")
            self._write(workspace_root / "tools" / "__init__.py", "")
            self._write(
                workspace_root / "tools" / "system.py",
                """
from core.interfaces.tools import tool

@tool(name="shared_ping", description="Simple ping tool.")
def shared_ping() -> dict:
    return {"ok": True}
""".strip(),
            )
            self._write(workspace_root / "agents" / "__init__.py", "")
            self._write(workspace_root / "agents" / "ops" / "__init__.py", "")
            self._write(
                workspace_root / "agents" / "ops" / "bot.py",
                """
from core.interfaces.agent import AgentModule, register_agent_class

@register_agent_class
class OpsBot(AgentModule):
    name = "Ops Bot"
    description = "Handles ops checks."
    system_prompt = "Use tools and keep responses concise."
    tools = ["shared_ping"]
""".strip(),
            )

            service = DiscoveryService(
                workspace_root=workspace_root,
                workspace_package="sandboxspace",
            )
            discovered = service.discover_agents()

            self.assertIn("ops.bot", discovered)
            definition = discovered["ops.bot"].definition
            self.assertEqual(definition.tools[0].name, "shared_ping")
            self.assertEqual(Register.get(ToolDefinition, "shared_ping").name, "shared_ping")

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + ("\n" if content else ""), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
