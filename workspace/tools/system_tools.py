from __future__ import annotations

from datetime import datetime, timezone

from core.contracts.tools import current_progress, tool


@tool(
    description="Return the current UTC time.",
    category="time",
    use_when=(
        "The question asks for the current time, current date, or needs an as-of timestamp.",
        "A time-sensitive answer should be anchored before searching for fresh information.",
    ),
    returns="A UTC timestamp in ISO 8601 format.",
    requires_current_data=True,
    follow_up_tools=("search_web",),
)
def get_current_utc_time() -> dict:
    progress = current_progress()
    progress.think(
        "Checking the current time",
        detail="Confirming the current UTC time before answering.",
        step_id="get_current_utc_time",
    )
    now = datetime.now(timezone.utc).isoformat()
    progress.think(
        "Current time confirmed",
        detail="The current UTC time has been confirmed.",
        step_id="get_current_utc_time",
        state="done",
    )
    progress.debug("Computed the current UTC timestamp.")
    return {"utc_time": now}


__all__ = ["get_current_utc_time"]
