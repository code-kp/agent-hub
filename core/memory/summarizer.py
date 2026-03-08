from __future__ import annotations

import asyncio
import os
import re
from uuid import uuid4

from google.adk.sessions import InMemorySessionService
from google.genai import types

import core.execution.shared.adk as shared_adk
from core.memory.context import MemoryMessage


SUMMARY_TIMEOUT_SECONDS = 15.0


def _sanitize_agent_identifier(agent_id: str) -> str:
    cleaned = re.sub(
        r"[^A-Za-z0-9_]+", "_", str(agent_id or "").strip().replace(".", "_")
    )
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "memory"
    if not re.match(r"^[A-Za-z_]", cleaned):
        cleaned = "_{value}".format(value=cleaned)
    return "{value}_memory_summary".format(value=cleaned)


class MemorySummarizer:
    def __init__(
        self,
        *,
        agent_id: str,
        model_name: str,
        timeout_seconds: float = SUMMARY_TIMEOUT_SECONDS,
    ) -> None:
        self.agent_id = agent_id
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    async def summarize(
        self,
        *,
        existing_summary: str,
        older_turns: list[MemoryMessage],
        max_summary_chars: int,
    ) -> str:
        if not older_turns:
            return existing_summary.strip()
        if not os.getenv("GOOGLE_API_KEY"):
            return _fallback_summary(
                existing_summary=existing_summary,
                older_turns=older_turns,
                max_summary_chars=max_summary_chars,
            )

        session_service = InMemorySessionService()
        session_id = "memory-{value}".format(value=uuid4())
        user_id = "memory-summarizer"
        created = session_service.create_session(
            app_name="agent_hub_memory",
            user_id=user_id,
            session_id=session_id,
        )
        if asyncio.iscoroutine(created):
            await created

        agent = shared_adk.create_llm_agent(
            agent_id=_sanitize_agent_identifier(self.agent_id),
            model_name=self.model_name,
            instruction=_summary_instruction(max_summary_chars=max_summary_chars),
            tool_callables=[],
            before_model_callback=lambda *_args, **_kwargs: None,
        )
        runner = shared_adk.create_runner(
            agent=agent,
            session_service=session_service,
            app_name="agent_hub_memory",
        )

        generated = ""
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async for event in shared_adk.stream_runner_events(
                    runner=runner,
                    user_id=user_id,
                    session_id=session_id,
                    new_message=types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text=_summary_message(
                                    existing_summary=existing_summary,
                                    older_turns=older_turns,
                                )
                            )
                        ],
                    ),
                    stream_output=False,
                ):
                    text = shared_adk.extract_text(event)
                    if getattr(event, "partial", False) and text:
                        generated += text
                    elif event.is_final_response() and text:
                        generated = shared_adk.merge_streamed_text(
                            streamed_text=generated,
                            final_event_text=text,
                        )
        except Exception:
            return _fallback_summary(
                existing_summary=existing_summary,
                older_turns=older_turns,
                max_summary_chars=max_summary_chars,
            )

        summarized = " ".join(generated.split()).strip()
        if not summarized:
            return _fallback_summary(
                existing_summary=existing_summary,
                older_turns=older_turns,
                max_summary_chars=max_summary_chars,
            )
        if len(summarized) > max_summary_chars:
            summarized = "{value}...".format(
                value=summarized[: max_summary_chars - 3].rstrip()
            )
        return summarized


def _summary_instruction(*, max_summary_chars: int) -> str:
    return "\n".join(
        [
            "You maintain compact conversation memory for future turns.",
            "Return a concise rolling memory note, not a transcript.",
            "Capture only high-value context:",
            "- the user's durable goal or preference",
            "- confirmed facts or decisions",
            "- unresolved follow-up threads that still matter",
            "Use short bullet-style sentences separated by semicolons.",
            "Do not include greetings, filler, or tool details unless they affect future answers.",
            "Do not exceed {limit} characters.".format(limit=max_summary_chars),
            "Return only the memory note.",
        ]
    )


def _summary_message(*, existing_summary: str, older_turns: list[MemoryMessage]) -> str:
    lines = []
    if existing_summary.strip():
        lines.extend(
            [
                "Existing memory summary:",
                existing_summary.strip(),
                "",
            ]
        )
    lines.append("Older turns to fold into memory:")
    for item in older_turns:
        lines.append("{role}: {text}".format(role=item.role, text=item.text))
    return "\n".join(lines)


def _fallback_summary(
    *,
    existing_summary: str,
    older_turns: list[MemoryMessage],
    max_summary_chars: int,
) -> str:
    bullets: list[str] = []
    if existing_summary.strip():
        bullets.append(existing_summary.strip())
    for item in older_turns[-6:]:
        bullets.append("{role}: {text}".format(role=item.role, text=item.text))
    compact = "; ".join(bullets)
    if len(compact) > max_summary_chars:
        compact = "{value}...".format(value=compact[: max_summary_chars - 3].rstrip())
    return compact
