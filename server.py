from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from api import service

app = FastAPI(title="Agent Hub Server")
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


def _parse_csv_field(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]


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


@app.post("/api/skills/upload")
async def upload_skill(
    file: UploadFile = File(...),
    user_id: str = Form("browser-user"),
    namespace: str = Form(""),
    title: Optional[str] = Form(None),
    summary: Optional[str] = Form(None),
    skill_type: str = Form("knowledge"),
    mode: str = Form("auto"),
    tags: Optional[str] = Form(None),
    triggers: Optional[str] = Form(None),
    priority: int = Form(60),
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
            title=title,
            summary=summary,
            skill_type=skill_type,
            mode=mode,
            tags=_parse_csv_field(tags),
            triggers=_parse_csv_field(triggers),
            priority=priority,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(
        {
            "skill": uploaded,
            "usage": {
                "recommended_type": "knowledge",
                "note": (
                    "Uploaded markdown is treated as user-scoped shared knowledge by default. "
                    "It is available across all agents for the same user id. "
                    "Use persona only for short, stable behavior-shaping instructions."
                ),
            },
        }
    )
