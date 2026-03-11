import unittest
from pathlib import Path

from core.platform import AgentPlatform


class WebAnswerTest(unittest.TestCase):
    def test_web_answer_prompt_requires_sources_and_more_detail(self) -> None:
        platform = AgentPlatform(Path("src/workspace"))
        _, _, runtime = platform.resolve_runtime("web.answer")

        self.assertIn("moderately detailed answer", runtime.definition.system_prompt)
        self.assertIn(
            "inline citations immediately after the supported sentence",
            runtime.definition.system_prompt,
        )
        self.assertIn("[1](https://example.com)", runtime.definition.system_prompt)
        self.assertIn(
            "do not add a separate Sources section", runtime.definition.system_prompt
        )
        self.assertTrue(runtime.definition.orchestration_configured)
        self.assertEqual(
            runtime.definition.hooks.__class__.__name__, "WebCitationHooks"
        )


if __name__ == "__main__":
    unittest.main()
