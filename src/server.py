"""
Tests:
- tests/test_server.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from api import api as service
from api import service as platform_service
from core.execution.shared.request_context import (
    bind_conversation_id,
    reset_conversation_id,
)
from services.ai import AiService, AiServiceError
from services.conversations import ConversationStore

app = FastAPI(title="Agent Hub Server")
ai_service = AiService(platform_service)
conversation_store = ConversationStore(
    Path(__file__).resolve().parent.parent / ".conversations"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_origin_regex=r"https?://(127\.0\.0\.1|localhost)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    agent_id: Optional[str] = None
    mode: Optional[str] = None
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: str = "browser-user"
    history: Optional[List["HistoryMessage"]] = None
    stream: bool = True


class AiRequest(BaseModel):
    agent_id: Optional[str] = None
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    instructions: str
    message: str


class HistoryMessage(BaseModel):
    role: str
    text: str


class ConversationsRequest(BaseModel):
    user_id: str = "browser-user"
    chats: List[dict[str, Any]] = []


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.get("/api/agents")
async def agents() -> JSONResponse:
    return JSONResponse(service.catalog())


@app.get("/api/models")
async def models() -> JSONResponse:
    return JSONResponse(service.list_available_models())


@app.get("/api/conversations")
async def conversations(user_id: str = "browser-user") -> JSONResponse:
    return JSONResponse({"chats": conversation_store.list_chats(user_id)})


@app.get("/api/conversations/session")
async def conversation_session(
    user_id: str = "browser-user",
    conversation_id: str = "",
    agent_id: str = "",
    mode: Optional[str] = None,
    model_id: Optional[str] = None,
    model_name: Optional[str] = None,
) -> JSONResponse:
    normalized_conversation_id = conversation_id.strip()
    normalized_agent_id = agent_id.strip()
    if not normalized_conversation_id or not normalized_agent_id:
        return JSONResponse({"session_id": None})

    try:
        selected_model_name = service.resolve_model_name(
            model_id=model_id,
            model_name=model_name,
        )
        resolved_agent_id, resolved_mode, _runtime = platform_service.resolve_runtime(
            normalized_agent_id,
            mode=mode,
            model_name=selected_model_name,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(
        {
            "session_id": conversation_store.session_id(
                user_id=user_id,
                conversation_id=normalized_conversation_id,
                agent_id=resolved_agent_id,
                mode=resolved_mode,
                model_name=selected_model_name,
            )
        }
    )


@app.put("/api/conversations")
async def save_conversations(payload: ConversationsRequest) -> JSONResponse:
    conversation_store.save_chats(payload.user_id, payload.chats)
    return JSONResponse({"ok": True})


@app.post("/api/chat/stream")
async def stream_chat(payload: ChatRequest) -> StreamingResponse:
    try:
        selected_model_name = service.resolve_model_name(
            model_id=payload.model_id,
            model_name=payload.model_name,
        )
        resolved_agent_id, resolved_mode, _runtime = platform_service.resolve_runtime(
            payload.agent_id,
            mode=payload.mode,
            model_name=selected_model_name,
        )
        stored_history = conversation_store.conversation_history(
            user_id=payload.user_id,
            conversation_id=payload.conversation_id,
        )
        stored_session_id = payload.session_id or conversation_store.session_id(
            user_id=payload.user_id,
            conversation_id=payload.conversation_id,
            agent_id=resolved_agent_id,
            mode=resolved_mode,
            model_name=selected_model_name,
        )
        request_history = (
            [item.model_dump() for item in payload.history]
            if payload.history
            else None
        )
        conversation_token = bind_conversation_id(payload.conversation_id)
        try:
            agent_id, mode, session_id, stream = await service.stream_chat(
                agent_id=payload.agent_id,
                mode=payload.mode,
                model_name=selected_model_name,
                message=payload.message,
                user_id=payload.user_id,
                session_id=stored_session_id,
                history=stored_history or request_history,
                stream=payload.stream,
            )
        finally:
            reset_conversation_id(conversation_token)
        conversation_store.save_session_id(
            user_id=payload.user_id,
            conversation_id=payload.conversation_id,
            agent_id=agent_id,
            mode=mode,
            model_name=selected_model_name,
            session_id=session_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "X-Agent-Id": agent_id,
        "X-Mode": mode,
        "X-Session-Id": session_id,
    }
    return StreamingResponse(stream, media_type="text/event-stream", headers=headers)


@app.post("/api/ai")
async def run_ai_request(payload: AiRequest) -> JSONResponse:
    try:
        selected_model_name = service.resolve_model_name(
            model_id=payload.model_id,
            model_name=payload.model_name,
        )
        text = await ai_service.generate_text(
            agent_id=payload.agent_id,
            model_name=selected_model_name,
            instructions=payload.instructions,
            message=payload.message,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AiServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(
        {
            "text": text,
        }
    )


@app.post("/api/skills/upload")
async def upload_skill(
    file: UploadFile = File(...),
    user_id: str = Form("browser-user"),
    namespace: str = Form(""),
) -> JSONResponse:
    file_name = (file.filename or "").strip()
    if not file_name:
        raise HTTPException(
            status_code=400, detail="Uploaded file is missing a filename."
        )
    if not file_name.lower().endswith(".md"):
        raise HTTPException(
            status_code=400, detail="Only markdown (.md) files are supported."
        )

    raw_content = await file.read()
    try:
        content = raw_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400, detail="Uploaded markdown must be valid UTF-8."
        ) from exc

    try:
        uploaded = service.upload_skill_markdown(
            file_name=file_name,
            content=content,
            uploader_id=user_id,
            namespace=namespace,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(
        {
            "skill": uploaded,
            "usage": {
                "note": (
                    "Uploaded markdown is treated as user-scoped knowledge. "
                    "It is available across all agents for the same user id."
                ),
            },
        }
    )
