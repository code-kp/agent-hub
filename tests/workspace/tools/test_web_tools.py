import unittest

from workspace.tools.web_tools import (
    _extract_page_content,
    _fetch_page_thinking_detail,
    _parse_duckduckgo_results,
    _search_thinking_detail,
)


class WebToolsTest(unittest.TestCase):
    def test_parse_duckduckgo_results_extracts_title_snippet_and_target_url(
        self,
    ) -> None:
        html = """
        <html>
          <body>
            <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fanswer">Example Answer</a>
            <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fanswer">
              Crisp summary from the web.
            </a>
          </body>
        </html>
        """

        results = _parse_duckduckgo_results(html, max_results=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Example Answer")
        self.assertEqual(results[0]["url"], "https://example.com/answer")
        self.assertEqual(results[0]["snippet"], "Crisp summary from the web.")

    def test_extract_page_content_strips_script_and_html_noise(self) -> None:
        html = """
        <html>
          <head>
            <title>Example Page</title>
            <script>console.log("ignore");</script>
          </head>
          <body>
            <main>
              <h1>Headline</h1>
              <p>Useful body text.</p>
            </main>
          </body>
        </html>
        """

        title, content = _extract_page_content(html, max_chars=200)

        self.assertEqual(title, "Example Page")
        self.assertIn("Headline", content)
        self.assertIn("Useful body text.", content)
        self.assertNotIn("console.log", content)

    def test_search_thinking_detail_includes_effective_query_for_time_sensitive_search(
        self,
    ) -> None:
        detail = _search_thinking_detail(
            original_query="latest OpenAI news",
            effective_query="latest OpenAI news March 7 2026",
            temporal_context={
                "time_sensitive": True,
                "current_date": "March 7 2026",
            },
        )

        self.assertIn("latest OpenAI news March 7 2026", detail)
        self.assertIn("current information", detail)

    def test_fetch_page_thinking_detail_mentions_source_host(self) -> None:
        detail = _fetch_page_thinking_detail("https://example.com/answer")

        self.assertEqual(detail, "Opening example.com to pull the relevant details.")


if __name__ == "__main__":
    unittest.main()
