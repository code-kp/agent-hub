from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
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
