"""
Tests:
- tests/test_server.py
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from api import service
from services.ai import AiService, AiServiceError

app = FastAPI(title="Agent Hub Server")
ai_service = AiService(service)
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
    session_id: Optional[str] = None
    user_id: str = "browser-user"
    history: Optional[List["HistoryMessage"]] = None
    stream: bool = True


class AiRequest(BaseModel):
    agent_id: Optional[str] = None
    instructions: str
    message: str


class HistoryMessage(BaseModel):
    role: str
    text: str


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.get("/api/agents")
async def agents() -> JSONResponse:
    return JSONResponse(service.catalog())


@app.post("/api/chat/stream")
async def stream_chat(payload: ChatRequest) -> StreamingResponse:
    try:
        agent_id, session_id, stream = await service.stream_chat(
            agent_id=payload.agent_id,
            message=payload.message,
            user_id=payload.user_id,
            session_id=payload.session_id,
            history=[item.model_dump() for item in payload.history] if payload.history else None,
            stream=payload.stream,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "X-Agent-Id": agent_id,
        "X-Session-Id": session_id,
    }
    return StreamingResponse(stream, media_type="text/event-stream", headers=headers)


@app.post("/api/ai")
async def run_ai_request(payload: AiRequest) -> JSONResponse:
    try:
        text = await ai_service.generate_text(
            agent_id=payload.agent_id,
            instructions=payload.instructions,
            message=payload.message,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
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
        raise HTTPException(status_code=400, detail="Uploaded file is missing a filename.")
    if not file_name.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="Only markdown (.md) files are supported.")

    raw_content = await file.read()
    try:
        content = raw_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Uploaded markdown must be valid UTF-8.") from exc

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
