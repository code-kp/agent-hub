import unittest
from pathlib import Path

from core.execution.orchestrated.runtime import OrchestratedAgentRuntime
from core.platform import AgentPlatform


class OrchestratedRuntimeTest(unittest.TestCase):
    def test_web_answer_uses_orchestrated_runtime_when_requested(self) -> None:
        platform = AgentPlatform(Path("src/workspace"))
        _, _, runtime = platform.resolve_runtime("web.answer", mode="orchestrated")

        self.assertIsInstance(runtime, OrchestratedAgentRuntime)


if __name__ == "__main__":
    unittest.main()
