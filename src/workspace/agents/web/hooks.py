"""
Tests:
- tests/workspace/agents/web/test_hooks.py
"""

from __future__ import annotations

import re
from typing import Any, Sequence

import core.contracts.hooks as contracts_hooks


_CITATION_GROUP_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\](?!\()")


class WebCitationHooks(contracts_hooks.AgentHooks):
    def create_turn_state(
        self,
        *,
        agent_id: str,
        user_id: str,
        session_id: str,
        message: str,
    ) -> contracts_hooks.HookState:
        return {"source_urls": []}

    def build_prompt_guidance(
        self,
        *,
        phase: str,
        state: contracts_hooks.HookState,
    ) -> str:
        if phase not in {"verifier", "writer"}:
            return ""

        source_urls = list(state.get("source_urls") or [])
        if not source_urls:
            return ""

        lines = [
            "When citing external evidence, use inline numeric references like [1] or [2].",
            "Only cite source numbers that appear in the numbered source catalog.",
            "Numbered source catalog:",
        ]
        for index, url in enumerate(source_urls, start=1):
            lines.append("{index}. {url}".format(index=index, url=url))
        return "\n".join(lines)

    def on_tool_response(
        self,
        *,
        state: contracts_hooks.HookState,
        tool_name: str,
        payload: Any,
    ) -> None:
        source_urls = state.setdefault("source_urls", [])
        if not isinstance(source_urls, list):
            source_urls = []
            state["source_urls"] = source_urls

        seen = set(str(item) for item in source_urls)
        for url in _extract_source_urls(tool_name, payload):
            if url in seen:
                continue
            source_urls.append(url)
            seen.add(url)

    def finalize_response(
        self,
        *,
        text: str,
        state: contracts_hooks.HookState,
    ) -> str:
        return _normalize_inline_citations(
            text=text,
            source_urls=list(state.get("source_urls") or []),
        )


def _extract_source_urls(tool_name: str, payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []

    if tool_name == "search_web":
        return _extract_search_web_urls(payload)

    if tool_name == "fetch_web_page":
        url = str(payload.get("url") or "").strip()
        return [url] if url else []

    return []


def _extract_search_web_urls(payload: dict[str, Any]) -> list[str]:
    results = payload.get("results") or []
    urls = []
    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if url:
            urls.append(url)
    return urls


def _normalize_inline_citations(text: str, source_urls: Sequence[str]) -> str:
    if not text or not source_urls:
        return text

    def replace(match: re.Match[str]) -> str:
        numbers = [part.strip() for part in match.group(1).split(",")]
        rendered = []
        changed = False

        for number in numbers:
            if not number.isdigit():
                rendered.append(number)
                continue

            index = int(number) - 1
            if 0 <= index < len(source_urls):
                rendered.append(
                    "[{number}]({url})".format(number=number, url=source_urls[index])
                )
                changed = True
            else:
                rendered.append("[{number}]".format(number=number))

        if not changed:
            return match.group(0)

        return ", ".join(rendered)

    return _CITATION_GROUP_RE.sub(replace, text)
