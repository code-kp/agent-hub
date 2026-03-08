import unittest

import core.contracts.hooks as contracts_hooks
from workspace.agents.web.hooks import WebCitationHooks


class WebCitationHooksTest(unittest.TestCase):
    def test_collects_unique_urls_in_order(self) -> None:
        hooks = WebCitationHooks()
        state = hooks.create_turn_state(
            agent_id="web.answer",
            user_id="user-1",
            session_id="session-1",
            message="What is the update?",
        )

        hooks.on_tool_response(
            state=state,
            tool_name="search_web",
            payload={
                "results": [
                    {"url": "https://example.com/1", "title": "One"},
                    {"url": "https://example.com/2", "title": "Two"},
                ]
            },
        )
        hooks.on_tool_response(
            state=state,
            tool_name="fetch_web_page",
            payload={
                "url": "https://example.com/2",
                "title": "Two",
                "content": "Detail",
            },
        )
        hooks.on_tool_response(
            state=state,
            tool_name="fetch_web_page",
            payload={
                "url": "https://example.com/3",
                "title": "Three",
                "content": "Detail",
            },
        )

        self.assertEqual(
            state["source_urls"],
            [
                "https://example.com/1",
                "https://example.com/2",
                "https://example.com/3",
            ],
        )

    def test_finalize_response_rewrites_bare_numeric_references(self) -> None:
        hooks = WebCitationHooks()
        state: contracts_hooks.HookState = {
            "source_urls": [
                "https://example.com/1",
                "https://example.com/2",
                "https://example.com/3",
                "https://example.com/4",
                "https://example.com/5",
            ]
        }
        text = (
            "Emirates is restoring service [5]. "
            "Check the official updates page for flight status [2, 4]."
        )
        normalized = hooks.finalize_response(
            text=text,
            state=state,
        )

        self.assertIn("[5](https://example.com/5)", normalized)
        self.assertIn(
            "[2](https://example.com/2), [4](https://example.com/4)", normalized
        )

    def test_finalize_response_leaves_existing_markdown_links_unchanged(self) -> None:
        hooks = WebCitationHooks()
        text = "The update is already cited [1](https://example.com/1)."
        normalized = hooks.finalize_response(
            text=text,
            state={"source_urls": ["https://example.com/1"]},
        )

        self.assertEqual(normalized, text)

    def test_verifier_guidance_renders_numbered_catalog(self) -> None:
        hooks = WebCitationHooks()
        guidance = hooks.build_prompt_guidance(
            phase="verifier",
            state={
                "source_urls": [
                    "https://example.com/1",
                    "https://example.com/2",
                ]
            },
        )

        self.assertIn("Numbered source catalog:", guidance)
        self.assertIn("1. https://example.com/1", guidance)
        self.assertIn("2. https://example.com/2", guidance)


if __name__ == "__main__":
    unittest.main()
