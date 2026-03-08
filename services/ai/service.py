from __future__ import annotations

import asyncio
import os
import re
from typing import Any
from uuid import uuid4

from google.adk.sessions import InMemorySessionService
from google.genai import types

from core.platform import AgentPlatform

import core.execution.shared.adk as shared_adk


AI_TIMEOUT_SECONDS = 20.0


class AiServiceError(ValueError):
    pass


def build_ui_agent_identifier(agent_id: str) -> str:
    cleaned = re.sub(
        r"[^A-Za-z0-9_]+", "_", str(agent_id or "").strip().replace(".", "_")
    )
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "ui"
    if not re.match(r"^[A-Za-z_]", cleaned):
        cleaned = "_{value}".format(value=cleaned)
    return "{value}_ui_request".format(value=cleaned)


class AiService:
    def __init__(self, platform: AgentPlatform) -> None:
        self.platform = platform

    async def generate_text(
        self,
        *,
        agent_id: str | None,
        instructions: str,
        message: str,
        timeout_seconds: float = AI_TIMEOUT_SECONDS,
    ) -> str:
        normalized_instructions = str(instructions or "").strip()
        normalized_message = str(message or "").strip()
        if not normalized_instructions:
            raise AiServiceError("instructions is required.")
        if not normalized_message:
            raise AiServiceError("message is required.")
        if not os.getenv("GOOGLE_API_KEY"):
            raise AiServiceError("Google API key is not configured.")

        resolved_agent_id, runtime = self.platform.resolve_runtime(agent_id)
        model_name = str(getattr(runtime, "model_name", "") or "").strip()
        if not model_name:
            raise AiServiceError("Could not resolve a model for the AI request.")

        session_service = InMemorySessionService()
        session_id = "ui-{value}".format(value=uuid4())
        user_id = "ui-request"
        created = session_service.create_session(
            app_name="agent_hub_ui",
            user_id=user_id,
            session_id=session_id,
        )
        if asyncio.iscoroutine(created):
            await created

        agent = shared_adk.create_llm_agent(
            agent_id=build_ui_agent_identifier(resolved_agent_id),
            model_name=model_name,
            instruction=normalized_instructions,
            tool_callables=[],
            before_model_callback=lambda *_args, **_kwargs: None,
        )
        runner = shared_adk.create_runner(
            agent=agent,
            session_service=session_service,
            app_name="agent_hub_ui",
        )

        generated = ""
        try:
            async with asyncio.timeout(timeout_seconds):
                user_content = types.Content(
                    role="user",
                    parts=[types.Part(text=normalized_message)],
                )
                async for event in shared_adk.stream_runner_events(
                    runner=runner,
                    user_id=user_id,
                    session_id=session_id,
                    new_message=user_content,
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
        except TimeoutError as exc:
            raise AiServiceError("Timed out waiting for the AI response.") from exc
        except Exception as exc:
            raise AiServiceError(str(exc) or "AI request failed.") from exc

        return generated.strip()
