import tempfile
import unittest
from pathlib import Path

from core.discovery import DiscoveryService
from core.contracts.skills import SkillDefinition
from core.contracts.tools import ToolDefinition, ensure_tools
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
                workspace_root / "skills" / "knowledge" / "support" / "triage.md",
                """
# Support Triage

Confirm the issue, environment, and recent changes.
""".strip(),
            )
            self._write(
                workspace_root / "tools" / "system.py",
                """
from core.contracts.tools import ToolModule, register_tool_class

@register_tool_class
class SharedPingTool(ToolModule):
    name = "shared_ping"
    description = "Simple ping tool."

    def run(self) -> dict:
        return {"ok": True}
""".strip(),
            )
            self._write(workspace_root / "agents" / "__init__.py", "")
            self._write(workspace_root / "agents" / "ops" / "__init__.py", "")
            self._write(
                workspace_root / "agents" / "ops" / "bot.py",
                """
from core.contracts.agent import AgentModule, register_agent_class

@register_agent_class
class OpsBot(AgentModule):
    name = "Ops Bot"
    description = "Handles ops checks."
    system_prompt = "Use tools and keep responses concise."
    tools = ["shared_ping"]
    knowledge = ["support.triage"]
""".strip(),
            )

            service = DiscoveryService(
                workspace_root=workspace_root,
                workspace_package="sandboxspace",
            )
            discovered_skills = service.discover_skills()
            discovered = service.discover_agents()

            self.assertIn("support.triage", discovered_skills)
            self.assertIn("ops.bot", discovered)
            definition = discovered["ops.bot"].definition
            self.assertEqual(
                [tool.name for tool in ensure_tools(definition.tools)],
                ["search_skills", "shared_ping"],
            )
            self.assertEqual(
                Register.get(ToolDefinition, "shared_ping").name, "shared_ping"
            )
            self.assertEqual(
                Register.get(SkillDefinition, "support.triage").title, "Support Triage"
            )

    def test_duplicate_ids_across_behavior_and_knowledge_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "sandboxspace"
            self._write(workspace_root / "__init__.py", "")
            self._write(workspace_root / "tools" / "__init__.py", "")
            self._write(workspace_root / "agents" / "__init__.py", "")
            self._write(
                workspace_root / "skills" / "behavior" / "support" / "persona.md",
                "# Support Persona\n\nKeep replies concrete.\n",
            )
            self._write(
                workspace_root / "skills" / "knowledge" / "support" / "persona.md",
                "# Support Persona Knowledge\n\nReference material.\n",
            )

            service = DiscoveryService(
                workspace_root=workspace_root,
                workspace_package="sandboxspace",
            )

            with self.assertRaises(RuntimeError):
                service.discover_skills()

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + ("\n" if content else ""), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
