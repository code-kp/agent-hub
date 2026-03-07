from __future__ import annotations

import json
import re
from html import unescape
from html.parser import HTMLParser
from typing import Dict, List, Tuple
from urllib.parse import parse_qs, quote_plus, urlparse, unquote
from urllib.request import Request, urlopen

from core.contracts.tools import current_progress, tool
from core.policies.search_strategy import SearchPlan, build_search_plan, build_search_plan_detail


DEFAULT_TIMEOUT_SECONDS = 12
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>")
TAG_RE = re.compile(r"(?s)<[^>]+>")
TITLE_RE = re.compile(r"(?is)<title[^>]*>(?P<title>.*?)</title>")
WHITESPACE_RE = re.compile(r"\s+")


class _DuckDuckGoResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: List[Dict[str, str]] = []
        self._current: Dict[str, str] | None = None
        self._capture_title = False
        self._capture_snippet = False

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())

        if tag == "a" and "result__a" in classes:
            self._finalize_current()
            href = _resolve_result_url(attributes.get("href", ""))
            self._current = {"title": "", "url": href, "snippet": ""}
            self._capture_title = True
            self._capture_snippet = False
            return

        if self._current and "result__snippet" in classes:
            self._capture_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_title:
            self._capture_title = False
            return
        if tag in {"a", "div", "span"} and self._capture_snippet:
            self._capture_snippet = False

    def handle_data(self, data: str) -> None:
        if not self._current:
            return
        if self._capture_title:
            self._current["title"] += data
        elif self._capture_snippet:
            self._current["snippet"] += data

    def close(self) -> None:
        super().close()
        self._finalize_current()

    def _finalize_current(self) -> None:
        if not self._current:
            return
        title = _clean_text(self._current.get("title", ""))
        url = self._current.get("url", "").strip()
        snippet = _clean_text(self._current.get("snippet", ""))
        if title and url:
            self.results.append({"title": title, "url": url, "snippet": snippet})
        self._current = None
        self._capture_title = False
        self._capture_snippet = False


@tool(
    description="Search the public web for recent answers and return concise result snippets.",
    category="public_web",
    use_when=(
        "The question depends on public information that may have changed.",
        "You need current events, company updates, prices, schedules, weather, scores, or other live information.",
    ),
    avoid_when=(
        "Internal guidance or direct reasoning already answers the question.",
    ),
    returns="Deduplicated web search results gathered from one or more query variants, with titles, URLs, and snippets.",
    requires_current_data=True,
    follow_up_tools=("fetch_web_page",),
)
def search_web(query: str, max_results: int = 5) -> dict:
    progress = current_progress()
    search_plan = build_search_plan(query)
    progress.think(
        "Checking recent sources",
        detail=build_search_plan_detail(search_plan),
        step_id="search_web",
    )
    progress.debug(
        "Searching the web.",
        query=query,
        effective_query=search_plan.effective_query,
        queries_used=list(search_plan.queries),
        max_results=max_results,
        time_sensitive=search_plan.time_sensitive,
    )

    query_runs = []
    results = _run_search_queries(
        search_plan=search_plan,
        max_results=max_results,
        query_runs=query_runs,
        progress=progress,
    )

    progress.think(
        "Recent sources checked",
        detail=_search_completion_detail(query_runs=query_runs, results=results),
        step_id="search_web",
        state="done",
    )
    progress.debug(
        "Web search completed.",
        matches=len(results),
        effective_query=search_plan.effective_query,
        queries_used=list(search_plan.queries),
    )
    return {
        "query": query,
        "effective_query": search_plan.effective_query,
        "queries_used": list(search_plan.queries),
        "query_runs": query_runs,
        "temporal_context": {
            "time_sensitive": search_plan.time_sensitive,
            "current_date": search_plan.current_date,
        },
        "results": results,
    }


@tool(
    description="Fetch a web page and extract readable text for summarization.",
    category="public_web",
    use_when=(
        "Search snippets are not enough and you need exact details from a specific public page.",
    ),
    returns="Readable page content extracted from the selected URL.",
)
def fetch_web_page(url: str, max_chars: int = 5000) -> dict:
    progress = current_progress()
    progress.think(
        "Reading the most relevant source",
        detail=_fetch_page_thinking_detail(url),
        step_id="fetch_web_page",
    )
    progress.debug("Fetching web page.", url=url)
    body = _http_get(url)
    title, content = _extract_page_content(body, max_chars=max_chars)
    progress.think(
        "Source details gathered",
        detail=_fetch_page_completed_detail(url),
        step_id="fetch_web_page",
        state="done",
    )
    progress.debug("Fetched web page.", title=title or "untitled", characters=len(content))
    return {"url": url, "title": title, "content": content}


def _http_get(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _search_web_instant_answer(query: str, max_results: int) -> List[Dict[str, str]]:
    body = _http_get(
        "https://api.duckduckgo.com/?q={query}&format=json&no_redirect=1&no_html=1&skip_disambig=1".format(
            query=quote_plus(query)
        )
    )
    payload = json.loads(body)
    results: List[Dict[str, str]] = []

    abstract_text = _clean_text(payload.get("AbstractText", ""))
    abstract_url = str(payload.get("AbstractURL", "") or "").strip()
    heading = _clean_text(payload.get("Heading", "")) or query
    if abstract_text and abstract_url:
        results.append(
            {
                "title": heading,
                "url": abstract_url,
                "snippet": abstract_text,
            }
        )

    for topic in payload.get("RelatedTopics", []):
        if len(results) >= max_results:
            break
        if isinstance(topic, dict) and "Topics" in topic:
            nested = topic.get("Topics") or []
        else:
            nested = [topic]
        for item in nested:
            if len(results) >= max_results:
                break
            if not isinstance(item, dict):
                continue
            text = _clean_text(item.get("Text", ""))
            url = str(item.get("FirstURL", "") or "").strip()
            if not text or not url:
                continue
            title = text.split(" - ", 1)[0].strip()
            results.append(
                {
                    "title": title or query,
                    "url": url,
                    "snippet": text,
                }
            )
    return results[:max_results]


def _run_search_queries(
    *,
    search_plan: SearchPlan,
    max_results: int,
    query_runs: List[Dict[str, object]],
    progress,
) -> List[Dict[str, str]]:
    deduped_results: List[Dict[str, str]] = []
    seen_urls = set()

    queries = list(search_plan.queries)
    for index, active_query in enumerate(queries, start=1):
        progress.think(
            "Checking recent sources",
            detail='Searching query {index}/{total}: "{query}".'.format(
                index=index,
                total=len(queries),
                query=active_query,
            ),
            step_id="search_web",
            state="running",
        )
        results = _search_web_once(active_query, max_results=max_results)
        query_runs.append(
            {
                "query": active_query,
                "matches": len(results),
            }
        )
        for item in results:
            url = str(item.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            deduped_results.append(item)
            if len(deduped_results) >= max_results:
                break
        if len(deduped_results) >= max_results:
            break

    return deduped_results[:max_results]


def _search_web_once(query: str, max_results: int) -> List[Dict[str, str]]:
    html = _http_get(
        "https://html.duckduckgo.com/html/?q={query}".format(query=quote_plus(query)),
    )
    results = _parse_duckduckgo_results(html, max_results=max_results)
    if not results:
        results = _search_web_instant_answer(query=query, max_results=max_results)
    return results[:max_results]


def _parse_duckduckgo_results(html: str, max_results: int) -> List[Dict[str, str]]:
    parser = _DuckDuckGoResultsParser()
    parser.feed(html)
    parser.close()
    return parser.results[:max_results]


def _extract_page_content(html: str, max_chars: int) -> Tuple[str, str]:
    title_match = TITLE_RE.search(html or "")
    title = _clean_text(title_match.group("title")) if title_match else ""
    stripped = SCRIPT_STYLE_RE.sub(" ", html or "")
    text = _clean_text(TAG_RE.sub(" ", stripped))
    if max_chars > 0 and len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return title, text


def _resolve_result_url(url: str) -> str:
    candidate = str(url or "").strip()
    if not candidate:
        return ""
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    parsed = urlparse(candidate)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [])
        if target:
            return unquote(target[0])
    return candidate


def _clean_text(value: str) -> str:
    text = unescape(str(value or ""))
    return WHITESPACE_RE.sub(" ", text).strip()


def _build_effective_query(query: str) -> Tuple[str, Dict[str, object]]:
    plan = build_search_plan(query, max_queries=1)
    return plan.effective_query, {
        "time_sensitive": plan.time_sensitive,
        "current_date": plan.current_date,
    }


def _build_search_queries(
    *,
    original_query: str,
    effective_query: str,
    temporal_context: Dict[str, object],
    max_queries: int = 3,
) -> List[str]:
    plan = build_search_plan(original_query, max_queries=max_queries)
    if effective_query and plan.effective_query != _clean_text(effective_query):
        plan = SearchPlan(
            original_query=plan.original_query,
            effective_query=_clean_text(effective_query),
            queries=plan.queries,
            time_sensitive=bool(temporal_context.get("time_sensitive")),
            current_date=str(temporal_context.get("current_date") or plan.current_date),
        )
    return list(plan.queries)


def _search_thinking_detail(
    *,
    original_query: str,
    effective_query: str,
    temporal_context: Dict[str, object],
) -> str:
    plan = SearchPlan(
        original_query=_clean_text(original_query),
        effective_query=_clean_text(effective_query),
        queries=(_clean_text(effective_query),),
        time_sensitive=bool(temporal_context.get("time_sensitive")),
        current_date=str(temporal_context.get("current_date") or "").strip(),
    )
    return build_search_plan_detail(plan)


def _fetch_page_thinking_detail(url: str) -> str:
    host = urlparse(str(url or "")).netloc.strip()
    if host:
        return "Opening {host} to pull the relevant details.".format(host=host)
    return "Opening the selected source to pull the relevant details."


def _fetch_page_completed_detail(url: str) -> str:
    host = urlparse(str(url or "")).netloc.strip()
    if host:
        return "Collected the relevant details from {host}.".format(host=host)
    return "Collected the relevant details from the selected source."


def _search_completion_detail(
    *,
    query_runs: List[Dict[str, object]],
    results: List[Dict[str, str]],
) -> str:
    queries = [
        '"{query}"'.format(query=str(item.get("query") or "").strip())
        for item in query_runs
        if str(item.get("query") or "").strip()
    ]
    if not queries:
        return "No search queries were executed."
    return "Ran {count} query variant(s): {queries}. Found {matches} unique result(s).".format(
        count=len(queries),
        queries=", ".join(queries),
        matches=len(results),
    )


__all__ = [
    "search_web",
    "fetch_web_page",
    "_build_search_queries",
    "_build_effective_query",
    "_extract_page_content",
    "_parse_duckduckgo_results",
    "_search_thinking_detail",
]
