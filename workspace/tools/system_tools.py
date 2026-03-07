from __future__ import annotations

from datetime import datetime, timezone

from core.interfaces.tools import current_progress, tool


@tool(description="Return the current UTC time.")
def get_current_utc_time() -> dict:
    progress = current_progress()
    now = datetime.now(timezone.utc).isoformat()
    progress.comment("Computed the current UTC timestamp.")
    return {"utc_time": now}


__all__ = ["get_current_utc_time"]
