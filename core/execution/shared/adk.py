from __future__ import annotations

import asyncio
import contextvars
import threading
from typing import Any, AsyncIterator, Callable, Sequence

from google.genai import types

try:
    from google.adk.agents import LlmAgent
except ImportError:  # pragma: no cover
    from google.adk.agent import Agent as LlmAgent  # type: ignore

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService


def create_llm_agent(
    *,
    agent_id: str,
    model_name: str,
    instruction: str,
    tool_callables: Sequence[Callable[..., Any]],
    before_model_callback: Callable[[Any, Any], Any],
) -> LlmAgent:
    return LlmAgent(
        name=agent_id.replace(".", "_"),
        model=model_name,
        instruction=instruction,
        tools=list(tool_callables),
        before_model_callback=before_model_callback,
    )


def create_runner(*, agent: LlmAgent, session_service: InMemorySessionService) -> Runner:
    return Runner(
        app_name="agent_hub",
        agent=agent,
        session_service=session_service,
    )


async def stream_runner_events(
    *,
    runner: Runner,
    user_id: str,
    session_id: str,
    new_message: types.Content,
) -> AsyncIterator[Any]:
    event_queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    context = contextvars.copy_context()

    async def produce() -> None:
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
            ):
                loop.call_soon_threadsafe(event_queue.put_nowait, ("event", event))
        except Exception as exc:
            loop.call_soon_threadsafe(event_queue.put_nowait, ("error", exc))
        finally:
            loop.call_soon_threadsafe(event_queue.put_nowait, ("done", None))

    def thread_main() -> None:
        context.run(lambda: asyncio.run(produce()))

    thread = threading.Thread(target=thread_main, daemon=True)
    thread.start()

    while True:
        kind, payload = await event_queue.get()
        if kind == "event":
            yield payload
            continue
        if kind == "error":
            raise payload
        break


def extract_text(event: Any) -> str:
    content = getattr(event, "content", None)
    if not content or not getattr(content, "parts", None):
        return ""
    parts = []
    for part in content.parts:
        text = getattr(part, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)
