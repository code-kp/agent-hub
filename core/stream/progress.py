from __future__ import annotations

import asyncio
import contextvars
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Optional

from core.stream.messages import build_thinking_message


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EventStream:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    loop: Optional[asyncio.AbstractEventLoop] = field(init=False, default=None)

    def __post_init__(self) -> None:
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None

    async def emit(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        body = {
            "type": event_type,
            "timestamp": utc_timestamp(),
        }
        if payload:
            body.update(payload)
        await self.queue.put(body)
        await asyncio.sleep(0)

    def emit_nowait(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        body = {
            "type": event_type,
            "timestamp": utc_timestamp(),
        }
        if payload:
            body.update(payload)
        if self.loop is None:
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                self.loop = None

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self.loop is not None and current_loop is not self.loop:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, body)
            return
        self.queue.put_nowait(body)

    async def close(self) -> None:
        await self.queue.put(None)

    async def sse_messages(self) -> AsyncIterator[str]:
        while True:
            event = await self.queue.get()
            if event is None:
                break
            payload = json.dumps(event, default=str)
            yield "event: {event_type}\ndata: {payload}\n\n".format(
                event_type=event["type"],
                payload=payload,
            )


_current_stream: contextvars.ContextVar[Optional[EventStream]] = contextvars.ContextVar(
    "current_progress_stream",
    default=None,
)


def bind_progress_stream(stream: EventStream) -> contextvars.Token:
    return _current_stream.set(stream)


def reset_progress_stream(token: contextvars.Token) -> None:
    _current_stream.reset(token)


async def emit_progress(event_type: str, **payload: Any) -> None:
    stream = _current_stream.get()
    if stream is not None:
        await stream.emit(event_type, payload)


def emit_progress_nowait(event_type: str, **payload: Any) -> None:
    stream = _current_stream.get()
    if stream is not None:
        stream.emit_nowait(event_type, payload)


async def emit_thinking_step(
    *,
    step_id: str,
    label: str,
    detail: str = "",
    state: str = "running",
    **payload: Any,
) -> None:
    await emit_progress(
        "thinking_step",
        channel="thinking",
        step_id=step_id,
        label=label,
        detail=detail,
        state=state,
        message=build_thinking_message(label, detail),
        **payload,
    )


def emit_thinking_step_nowait(
    *,
    step_id: str,
    label: str,
    detail: str = "",
    state: str = "running",
    **payload: Any,
) -> None:
    emit_progress_nowait(
        "thinking_step",
        channel="thinking",
        step_id=step_id,
        label=label,
        detail=detail,
        state=state,
        message=build_thinking_message(label, detail),
        **payload,
    )


async def emit_debug_event(event_type: str, **payload: Any) -> None:
    await emit_progress(event_type, channel="debug", **payload)


def emit_debug_event_nowait(event_type: str, **payload: Any) -> None:
    emit_progress_nowait(event_type, channel="debug", **payload)
