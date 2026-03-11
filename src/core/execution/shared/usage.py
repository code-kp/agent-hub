from __future__ import annotations

from typing import Any


USAGE_COUNT_FIELDS = (
    "prompt_token_count",
    "candidates_token_count",
    "tool_use_prompt_token_count",
    "thoughts_token_count",
    "cached_content_token_count",
    "total_token_count",
)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _extract_text(event: Any) -> str:
    content = getattr(event, "content", None)
    if not content or not getattr(content, "parts", None):
        return ""
    parts: list[str] = []
    for part in content.parts:
        text = getattr(part, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


def _event_has_usage_content(event: Any) -> bool:
    if _extract_text(event):
        return True
    if list(getattr(event, "get_function_calls", lambda: [])() or []):
        return True
    if getattr(event, "error_code", None):
        return True
    if getattr(event, "finish_reason", None):
        return True
    if getattr(event, "turn_complete", False):
        return True
    return bool(getattr(event, "interaction_id", None))


def _usage_call_from_event(event: Any) -> dict[str, Any] | None:
    usage = getattr(event, "usage_metadata", None)
    if usage is None or getattr(event, "partial", False):
        return None
    if not _event_has_usage_content(event):
        return None

    prompt_tokens = _as_int(getattr(usage, "prompt_token_count", 0))
    output_tokens = _as_int(getattr(usage, "candidates_token_count", 0))
    tool_use_prompt_tokens = _as_int(getattr(usage, "tool_use_prompt_token_count", 0))
    thoughts_tokens = _as_int(getattr(usage, "thoughts_token_count", 0))
    cached_content_tokens = _as_int(getattr(usage, "cached_content_token_count", 0))
    total_tokens = _as_int(getattr(usage, "total_token_count", 0))

    return {
        "event_id": str(getattr(event, "id", "") or ""),
        "author": str(getattr(event, "author", "") or ""),
        "model_version": str(getattr(event, "model_version", "") or ""),
        "interaction_id": str(getattr(event, "interaction_id", "") or ""),
        "input_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "tool_use_prompt_tokens": tool_use_prompt_tokens,
        "thoughts_tokens": thoughts_tokens,
        "cached_content_tokens": cached_content_tokens,
        "total_tokens": total_tokens,
    }


class UsageAggregator:
    def __init__(self) -> None:
        self._seen_event_ids: set[str] = set()
        self._calls: list[dict[str, Any]] = []

    def record_event(self, event: Any) -> None:
        call = _usage_call_from_event(event)
        if call is None:
            return

        event_id = call.get("event_id") or ""
        if event_id and event_id in self._seen_event_ids:
            return
        if event_id:
            self._seen_event_ids.add(event_id)

        self._calls.append(call)

    def summary(self) -> dict[str, Any] | None:
        if not self._calls:
            return None

        return {
            "call_count": len(self._calls),
            "input_tokens": sum(call["input_tokens"] for call in self._calls),
            "output_tokens": sum(call["output_tokens"] for call in self._calls),
            "tool_use_prompt_tokens": sum(
                call["tool_use_prompt_tokens"] for call in self._calls
            ),
            "thoughts_tokens": sum(call["thoughts_tokens"] for call in self._calls),
            "cached_content_tokens": sum(
                call["cached_content_tokens"] for call in self._calls
            ),
            "total_tokens": sum(call["total_tokens"] for call in self._calls),
            "calls": [
                {
                    key: value
                    for key, value in call.items()
                    if key != "event_id" and value not in ("", None)
                }
                for call in self._calls
            ],
        }
