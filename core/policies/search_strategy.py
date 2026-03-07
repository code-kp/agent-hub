from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone


WHITESPACE_RE = re.compile(r"\s+")
STOPWORD_RE = re.compile(
    r"\b("
    r"a|an|the|is|are|was|were|be|being|been|do|does|did|how|what|when|where|why|who|"
    r"tell|me|about|for|with|from|into|onto|of|to|in|on|at|and|or|please|latest|recent|current"
    r")\b",
    re.IGNORECASE,
)
TEMPORAL_QUERY_RE = re.compile(
    r"\b("
    r"today|latest|recent|current|currently|now|right now|as of|live|breaking|newest|"
    r"this week|this month|this year|yesterday|tomorrow|news|headline|update|updated|"
    r"score|scores|price|prices|weather|forecast|schedule|schedules"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SearchPlan:
    original_query: str
    effective_query: str
    queries: tuple[str, ...]
    time_sensitive: bool
    current_date: str


def build_search_plan(
    query: str,
    *,
    now: datetime | None = None,
    max_queries: int = 3,
) -> SearchPlan:
    normalized_query = clean_text(query)
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    current_date_label = "{month} {day} {year}".format(
        month=current_time.strftime("%B"),
        day=current_time.day,
        year=current_time.year,
    )
    time_sensitive = query_needs_current_date_context(normalized_query)
    effective_query = normalized_query
    if time_sensitive and normalized_query:
        effective_query = "{query} {date}".format(query=normalized_query, date=current_date_label).strip()

    queries: list[str] = []
    add_query(queries, effective_query)
    add_query(queries, normalized_query)

    keyword_query = build_keyword_query(normalized_query)
    if time_sensitive and keyword_query:
        add_query(
            queries,
            "{query} {date}".format(
                query=keyword_query,
                date=current_date_label,
            ),
        )
    elif keyword_query:
        add_query(queries, keyword_query)

    return SearchPlan(
        original_query=normalized_query,
        effective_query=effective_query,
        queries=tuple(queries[:max_queries]),
        time_sensitive=time_sensitive,
        current_date=current_date_label,
    )


def build_search_plan_detail(plan: SearchPlan) -> str:
    if plan.time_sensitive and plan.effective_query != plan.original_query:
        return 'Searching for "{query}" so the results stay anchored to current information.'.format(
            query=plan.effective_query,
        )
    return 'Searching for "{query}" on the public web.'.format(query=plan.effective_query)


def query_needs_current_date_context(query: str) -> bool:
    normalized = clean_text(query).lower()
    if not normalized:
        return False
    return bool(TEMPORAL_QUERY_RE.search(normalized))


def build_keyword_query(query: str) -> str:
    normalized = clean_text(query)
    if not normalized:
        return ""
    lowered = STOPWORD_RE.sub(" ", normalized)
    lowered = WHITESPACE_RE.sub(" ", lowered).strip()
    return lowered if len(lowered) >= 3 else ""


def clean_text(value: str) -> str:
    return WHITESPACE_RE.sub(" ", str(value or "")).strip()


def add_query(queries: list[str], value: str) -> None:
    normalized = clean_text(value)
    if not normalized or normalized in queries:
        return
    queries.append(normalized)
