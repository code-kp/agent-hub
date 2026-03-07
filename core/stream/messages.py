from __future__ import annotations

import json
from typing import Any, Iterable, Mapping


def ensure_sentence(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    if cleaned[-1] in ".!?":
        return cleaned
    return "{text}.".format(text=cleaned)


def humanize_key(value: str) -> str:
    return str(value or "").replace("_", " ").strip()


def compact_text(value: str, *, limit: int = 96) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return "{prefix}...".format(prefix=text[: limit - 3].rstrip())


def summarize_value(value: Any, *, limit: int = 64) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        text = compact_text(value, limit=limit)
        return '"{text}"'.format(text=text) if " " in text else text
    if isinstance(value, Mapping):
        items = list(value.items())
        if not items:
            return "no fields"
        parts = [
            "{key}={value}".format(
                key=humanize_key(key),
                value=summarize_value(item_value, limit=28),
            )
            for key, item_value in items[:3]
        ]
        if len(items) > 3:
            parts.append("+{count} more".format(count=len(items) - 3))
        return ", ".join(parts)
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        if not items:
            return "none"
        if len(items) <= 3 and all(not isinstance(item, (dict, list, tuple, set)) for item in items):
            return ", ".join(summarize_value(item, limit=20).strip('"') for item in items)
        return "{count} items".format(count=len(items))
    try:
        return compact_text(json.dumps(value, default=str), limit=limit)
    except TypeError:
        return compact_text(str(value), limit=limit)


def format_named_values(values: Mapping[str, Any], *, prefix: str = "Details") -> str:
    relevant = [
        "{key}={value}".format(
            key=humanize_key(key),
            value=summarize_value(value),
        )
        for key, value in values.items()
        if value not in (None, "", [], {}, ())
    ]
    if not relevant:
        return ""
    return "{prefix}: {items}.".format(prefix=prefix, items="; ".join(relevant))


def build_progress_message(message: str, **payload: Any) -> str:
    base = ensure_sentence(message or "Progress update")
    details = format_named_values(payload)
    if not details:
        return base
    return "{base} {details}".format(base=base, details=details)


def build_thinking_message(label: str, detail: str = "") -> str:
    headline = ensure_sentence(label or "Working through the request")
    trailing = ensure_sentence(detail or "")
    if trailing:
        return "{headline} {detail}".format(headline=headline, detail=trailing)
    return headline


def build_run_started_message(agent_label: str) -> str:
    label = agent_label.strip() or "the selected agent"
    return "Started a new run with {label}.".format(label=label)


def build_run_completed_message(agent_label: str) -> str:
    label = agent_label.strip() or "the selected agent"
    return "Completed the response from {label}.".format(label=label)


def build_skill_context_message(chunks: Iterable[Any]) -> str:
    items = list(chunks)
    if not items:
        return "No saved skill context was needed for this request."

    def read_field(chunk: Any, key: str) -> str:
        if isinstance(chunk, Mapping):
            return str(chunk.get(key, "") or "")
        return str(getattr(chunk, key, "") or "")

    sources: list[str] = []
    for chunk in items:
        source = read_field(chunk, "source")
        if source and source not in sources:
            sources.append(source)

    if len(items) == 1:
        source = read_field(items[0], "source") or "the skill library"
        heading = read_field(items[0], "heading") or "a relevant section"
        return "Loaded 1 relevant skill excerpt from {source} ({heading}).".format(
            source=source,
            heading=heading,
        )

    preview_sources = ", ".join(sources[:3]) if sources else "the skill library"
    if len(sources) > 3:
        preview_sources = "{sources}, and {count} more".format(
            sources=preview_sources,
            count=len(sources) - 3,
        )
    return "Loaded {count} relevant skill excerpts from {sources}.".format(
        count=len(items),
        sources=preview_sources,
    )


def build_tool_selection_message(tool_name: str, reason: str) -> str:
    clean_reason = ensure_sentence(reason or "")
    if clean_reason:
        return "Choosing {tool}. {reason}".format(tool=tool_name or "the next tool", reason=clean_reason)
    return "Choosing {tool} for the next step.".format(tool=tool_name or "the next tool")


def build_tool_started_message(tool_name: str, args: Mapping[str, Any] | None) -> str:
    details = format_named_values(dict(args or {}), prefix="Inputs")
    if details:
        return "Running {tool}. {details}".format(tool=tool_name or "tool", details=details)
    return "Running {tool}.".format(tool=tool_name or "tool")


def build_tool_completed_message(tool_name: str, response: Any) -> str:
    if isinstance(response, Mapping):
        if isinstance(response.get("results"), list):
            return "{tool} finished and found {count} result(s).".format(
                tool=tool_name or "Tool",
                count=len(response["results"]),
            )
        if isinstance(response.get("skills"), list):
            return "{tool} finished and listed {count} skill file(s).".format(
                tool=tool_name or "Tool",
                count=len(response["skills"]),
            )
        if "content" in response:
            return "{tool} finished and loaded the requested file.".format(
                tool=tool_name or "Tool"
            )
        if len(response) == 1:
            key, value = next(iter(response.items()))
            return "{tool} finished. {key}: {value}.".format(
                tool=tool_name or "Tool",
                key=humanize_key(str(key)).capitalize(),
                value=summarize_value(value, limit=84).strip('"'),
            )
        details = format_named_values(dict(response), prefix="Returned")
        if details:
            return "{tool} finished. {details}".format(tool=tool_name or "Tool", details=details)

    if isinstance(response, list):
        return "{tool} finished and returned {count} item(s).".format(
            tool=tool_name or "Tool",
            count=len(response),
        )

    if response not in (None, ""):
        return "{tool} finished. Result: {value}.".format(
            tool=tool_name or "Tool",
            value=summarize_value(response, limit=84).strip('"'),
        )
    return "{tool} finished.".format(tool=tool_name or "Tool")


def build_error_message(error: str) -> str:
    clean_error = ensure_sentence(error or "Unknown error")
    return "The run failed. {error}".format(error=clean_error)
