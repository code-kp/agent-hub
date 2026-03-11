from __future__ import annotations

import asyncio
import contextvars
import threading
from typing import Any, AsyncIterator, Callable, Sequence

from google.genai import types
from google.adk.agents.run_config import RunConfig, StreamingMode

try:
    from google.adk.agents import LlmAgent
except ImportError:  # pragma: no cover
    from google.adk.agent import Agent as LlmAgent  # type: ignore

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService


def create_llm_agent(
    *,
    agent_id: str,
    model: Any,
    instruction: str,
    tool_callables: Sequence[Callable[..., Any]],
    before_model_callback: Callable[[Any, Any], Any],
    generate_content_config: types.GenerateContentConfig | None = None,
) -> LlmAgent:
    return LlmAgent(
        name=agent_id.replace(".", "_"),
        model=model,
        instruction=instruction,
        tools=list(tool_callables),
        before_model_callback=before_model_callback,
        generate_content_config=generate_content_config,
    )


def create_runner(
    *,
    agent: LlmAgent,
    session_service: InMemorySessionService,
    app_name: str = "agent_hub",
) -> Runner:
    return Runner(
        app_name=app_name,
        agent=agent,
        session_service=session_service,
    )


async def stream_runner_events(
    *,
    runner: Runner,
    user_id: str,
    session_id: str,
    new_message: types.Content,
    stream_output: bool = True,
) -> AsyncIterator[Any]:
    event_queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    context = contextvars.copy_context()
    run_config = RunConfig(
        streaming_mode=StreamingMode.SSE if stream_output else StreamingMode.NONE,
    )

    async def produce() -> None:
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
                run_config=run_config,
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


def build_generate_content_config(
    *, model_name: str = "", include_thoughts: bool = False
) -> types.GenerateContentConfig | None:
    if not include_thoughts:
        return None
    normalized_model = str(model_name or "").strip().lower()
    thinking_config = types.ThinkingConfig(include_thoughts=True)

    # Gemini 3 uses thinking_level instead of the older thinking_budget control.
    if normalized_model.startswith("gemini-3"):
        thinking_config.thinking_level = types.ThinkingLevel.LOW
    else:
        thinking_config.thinking_budget = -1

    return types.GenerateContentConfig(thinking_config=thinking_config)


def _extract_text_parts(
    event: Any,
    *,
    include_thoughts: bool,
    thoughts_only: bool,
) -> str:
    content = getattr(event, "content", None)
    if not content or not getattr(content, "parts", None):
        return ""
    parts = []
    for part in content.parts:
        text = getattr(part, "text", None)
        is_thought = bool(getattr(part, "thought", False))
        if not text:
            continue
        if thoughts_only and not is_thought:
            continue
        if not thoughts_only and is_thought and not include_thoughts:
            continue
        if text:
            parts.append(text)
    return "".join(parts)


def extract_text(event: Any, *, include_thoughts: bool = False) -> str:
    return _extract_text_parts(
        event,
        include_thoughts=include_thoughts,
        thoughts_only=False,
    )


def extract_thought_text(event: Any) -> str:
    return _extract_text_parts(
        event,
        include_thoughts=True,
        thoughts_only=True,
    )


def merge_streamed_text(*, streamed_text: str, final_event_text: str) -> str:
    if not streamed_text:
        return final_event_text
    if not final_event_text:
        return streamed_text
    if final_event_text == streamed_text:
        return final_event_text
    if final_event_text.startswith(streamed_text):
        return final_event_text
    if streamed_text.endswith(final_event_text):
        return streamed_text
    overlap = min(len(streamed_text), len(final_event_text))
    while overlap > 0:
        if streamed_text.endswith(final_event_text[:overlap]):
            return "{buffer}{tail}".format(
                buffer=streamed_text,
                tail=final_event_text[overlap:],
            )
        overlap -= 1
    return "{buffer}{tail}".format(buffer=streamed_text, tail=final_event_text)
