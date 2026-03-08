import unittest
from pathlib import Path

from core.platform import AgentPlatform


class WebResearchTest(unittest.TestCase):
    def test_web_research_definition_is_orchestrated(self) -> None:
        platform = AgentPlatform(Path("workspace"))
        runtime = platform._runtimes["web.research"]

        self.assertEqual(runtime.definition.runtime_mode, "orchestrated")
        self.assertEqual(
            runtime.definition.hooks.__class__.__name__, "WebCitationHooks"
        )


if __name__ == "__main__":
    unittest.main()
