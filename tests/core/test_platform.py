import unittest
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core.contracts.agent import define_agent
from core.discovery import DiscoveredAgent
from core.execution import DirectAgentRuntime, OrchestratedAgentRuntime
from core.platform import AgentPlatform


class AgentPlatformTest(unittest.TestCase):
    def test_catalog_lists_web_agents(self) -> None:
        platform = AgentPlatform(Path("src/workspace"))
        catalog = platform.catalog()
        agents_by_id = {agent["id"]: agent for agent in catalog["agents"]}
        agent_ids = list(agents_by_id.keys())

        self.assertIn("web.answer", agent_ids)
        self.assertEqual(agents_by_id["general"]["runtime_modes"], ["direct"])
        self.assertFalse(agents_by_id["general"]["orchestration_configured"])
        self.assertEqual(
            agents_by_id["web.answer"]["runtime_modes"],
            ["direct", "orchestrated"],
        )
        self.assertTrue(agents_by_id["web.answer"]["orchestration_configured"])
        self.assertEqual(agents_by_id["web.answer"]["default_mode"], "direct")

    def test_resolve_runtime_accepts_explicit_direct_and_orchestrated_modes(self) -> None:
        platform = AgentPlatform(Path("src/workspace"))

        _, direct_mode, direct_runtime = platform.resolve_runtime(
            "web.answer",
            mode="direct",
        )
        _, orchestrated_mode, orchestrated_runtime = platform.resolve_runtime(
            "web.answer",
            mode="orchestrated",
        )

        self.assertEqual(direct_mode, "direct")
        self.assertIsInstance(direct_runtime, DirectAgentRuntime)
        self.assertEqual(orchestrated_mode, "orchestrated")
        self.assertIsInstance(orchestrated_runtime, OrchestratedAgentRuntime)

    def test_resolve_runtime_uses_distinct_runtimes_for_distinct_model_overrides(
        self,
    ) -> None:
        platform = AgentPlatform(Path("src/workspace"))

        _, _, first_runtime = platform.resolve_runtime(
            "web.answer",
            model_name="gemini-2.0-flash",
        )
        _, _, second_runtime = platform.resolve_runtime(
            "web.answer",
            model_name="litellm:openai/gpt-4o-mini",
        )

        self.assertNotEqual(first_runtime.model_name, second_runtime.model_name)

    def test_resolve_runtime_rejects_orchestrated_for_agents_without_config(self) -> None:
        platform = AgentPlatform(Path("src/workspace"))

        with self.assertRaises(ValueError):
            platform.resolve_runtime("general", mode="orchestrated")

    def test_refresh_reloads_dotenv_and_rebuilds_runtimes(self) -> None:
        original_model_name = os.environ.pop("MODEL_NAME", None)
        original_model_backend = os.environ.pop("MODEL_BACKEND", None)

        try:
            with TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                workspace_root = root / "workspace"
                workspace_root.mkdir()
                dotenv_path = root / ".env"
                dotenv_path.write_text(
                    'MODEL_NAME="gemini-3.1-flash-lite-preview"\nMODEL_BACKEND="litellm"\n',
                    encoding="utf-8",
                )

                discovered = {
                    "general": DiscoveredAgent(
                        agent_id="general",
                        module_name="workspace.agents.general",
                        project_name="workspace",
                        project_root=workspace_root,
                        definition=define_agent(
                            name="General Assistant",
                            description="General-purpose assistant.",
                            system_prompt="Answer clearly.",
                        ),
                        fingerprint="general-fingerprint",
                    )
                }

                runtimes_created = []

                def fake_create_agent_runtime(record, *, runtime_mode=None, model_name=None):
                    runtime = {
                        "agent_id": record.agent_id,
                        "runtime_mode": runtime_mode,
                        "model_name": model_name or os.getenv("MODEL_NAME"),
                        "model_backend": os.getenv("MODEL_BACKEND"),
                    }
                    runtimes_created.append(runtime)
                    return runtime

                with patch(
                    "core.platform.DiscoveryService.discover_skills",
                    return_value={},
                ), patch(
                    "core.platform.DiscoveryService.discover_agents",
                    return_value=discovered,
                ), patch(
                    "core.platform.create_agent_runtime",
                    side_effect=fake_create_agent_runtime,
                ):
                    platform = AgentPlatform(workspace_root)
                    _, _, first_runtime = platform.resolve_runtime("general")

                    self.assertEqual(first_runtime["model_name"], "gemini-3.1-flash-lite-preview")
                    self.assertEqual(first_runtime["model_backend"], "litellm")

                    dotenv_path.write_text(
                        'MODEL_NAME="gemini-3.1-flash-lite-preview"\n',
                        encoding="utf-8",
                    )
                    platform.refresh()
                    _, _, second_runtime = platform.resolve_runtime("general")

                    self.assertEqual(second_runtime["model_name"], "gemini-3.1-flash-lite-preview")
                    self.assertIsNone(second_runtime["model_backend"])
                    self.assertIsNone(os.getenv("MODEL_BACKEND"))
                    self.assertIsNot(first_runtime, second_runtime)
                    self.assertEqual(len(runtimes_created), 2)
        finally:
            if original_model_name is not None:
                os.environ["MODEL_NAME"] = original_model_name
            else:
                os.environ.pop("MODEL_NAME", None)

            if original_model_backend is not None:
                os.environ["MODEL_BACKEND"] = original_model_backend
            else:
                os.environ.pop("MODEL_BACKEND", None)


if __name__ == "__main__":
    unittest.main()
