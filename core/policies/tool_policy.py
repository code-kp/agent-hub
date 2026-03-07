from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from core.contracts.tools import ToolDefinition
from core.skills.resolver import ResolvedSkillContext


TEMPORAL_QUERY_RE = re.compile(
    r"\b("
    r"today|latest|recent|current|currently|now|right now|as of|live|breaking|newest|"
    r"this week|this month|this year|yesterday|tomorrow|news|headline|update|updated|"
    r"score|scores|price|prices|weather|forecast|schedule|schedules"
    r")\b",
    re.IGNORECASE,
)
EXACT_TIME_RE = re.compile(
    r"\b("
    r"what time|current time|time now|today(?:'s| is)? date|current date|what day|day is it|utc time"
    r")\b",
    re.IGNORECASE,
)
PUBLIC_WEB_RE = re.compile(
    r"\b("
    r"news|headline|breaking|price|prices|stock|weather|forecast|score|scores|"
    r"schedule|release|released|launch|announced|announcement|ceo|president|election|market|exchange rate"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class IntentAnalysis:
    query: str
    is_temporal: bool
    asks_for_exact_time: bool
    needs_public_web: bool
    should_anchor_to_current_time: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlannedToolCall:
    tool_name: str
    tool_args: Dict[str, Any]
    rationale: str


@dataclass(frozen=True)
class ToolExecutionPlan:
    intent: IntentAnalysis
    preflight_calls: tuple[PlannedToolCall, ...] = ()


def analyze_intent(query: str, resolved_context: ResolvedSkillContext) -> IntentAnalysis:
    normalized_query = " ".join(str(query or "").split()).strip()
    lowered = normalized_query.lower()
    is_temporal = bool(TEMPORAL_QUERY_RE.search(lowered))
    asks_for_exact_time = bool(EXACT_TIME_RE.search(lowered))
    explicit_public_request = bool(PUBLIC_WEB_RE.search(lowered))
    has_internal_guidance = not resolved_context.is_empty

    needs_public_web = (
        not asks_for_exact_time
        and (
            explicit_public_request
            or (is_temporal and not has_internal_guidance)
        )
    )
    should_anchor_to_current_time = is_temporal or asks_for_exact_time

    reasons = []
    if asks_for_exact_time:
        reasons.append("The request asks for the current time or date.")
    elif is_temporal:
        reasons.append("The request is time-sensitive.")
    if explicit_public_request:
        reasons.append("The request points to public information that may have changed.")
    if has_internal_guidance:
        reasons.append("Relevant internal guidance is available.")

    return IntentAnalysis(
        query=normalized_query,
        is_temporal=is_temporal,
        asks_for_exact_time=asks_for_exact_time,
        needs_public_web=needs_public_web,
        should_anchor_to_current_time=should_anchor_to_current_time,
        reasons=tuple(reasons),
    )


def plan_tool_execution(
    *,
    query: str,
    available_tools: Sequence[ToolDefinition],
    resolved_context: ResolvedSkillContext,
) -> ToolExecutionPlan:
    intent = analyze_intent(query, resolved_context)
    time_tool = _pick_tool(available_tools, preferred_name="get_current_utc_time", category="time")
    public_web_tool = _pick_tool(available_tools, preferred_name="search_web", category="public_web")
    calls = []

    if intent.should_anchor_to_current_time and time_tool is not None:
        calls.append(
            PlannedToolCall(
                tool_name=time_tool.name,
                tool_args={},
                rationale=(
                    "The request needs a current time anchor before answering."
                    if not intent.asks_for_exact_time
                    else "The request explicitly asks for the current time or date."
                ),
            )
        )

    if intent.needs_public_web and public_web_tool is not None:
        calls.append(
            PlannedToolCall(
                tool_name=public_web_tool.name,
                tool_args={"query": query},
                rationale=(
                    "The request needs fresh public information, so web search should run before the model answers."
                ),
            )
        )

    return ToolExecutionPlan(intent=intent, preflight_calls=tuple(calls))


def format_intent_for_thinking(intent: IntentAnalysis) -> str:
    if intent.asks_for_exact_time:
        return "This looks like a direct time lookup, so the current time is being checked first."
    if intent.needs_public_web and intent.should_anchor_to_current_time:
        return "This looks current and public-facing, so the current time is being checked before searching fresh sources."
    if intent.needs_public_web:
        return "This looks like public information that may have changed, so fresh sources are being checked."
    if intent.should_anchor_to_current_time:
        return "This answer benefits from a current time anchor before responding."
    return "The available guidance looks sufficient, so no required preflight tools are needed."


def _pick_tool(
    available_tools: Sequence[ToolDefinition],
    *,
    preferred_name: str,
    category: str,
) -> Optional[ToolDefinition]:
    for tool in available_tools:
        if tool.name == preferred_name:
            return tool
    for tool in available_tools:
        if tool.category == category:
            return tool
    return None
