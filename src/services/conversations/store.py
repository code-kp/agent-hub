from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_SAFE_USER_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class ConversationStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def list_chats(self, user_id: str) -> list[dict[str, Any]]:
        payload = self._read_user_payload(user_id)
        chats = payload.get("chats")
        if not isinstance(chats, list):
            return []
        return [self._normalize_chat(item) for item in chats if isinstance(item, dict)]

    def save_chats(self, user_id: str, chats: list[dict[str, Any]]) -> None:
        normalized_chats = [
            self._normalize_chat(item) for item in chats if isinstance(item, dict)
        ]
        existing_payload = self._read_user_payload(user_id)
        payload = {
            **{
                key: value
                for key, value in existing_payload.items()
                if key not in {"user_id", "chats", "sessions"}
            },
            "user_id": str(user_id or "").strip() or "browser-user",
            "chats": normalized_chats,
            "sessions": self._prune_sessions(
                existing_payload.get("sessions"),
                {
                    str(chat.get("id") or "").strip()
                    for chat in normalized_chats
                    if str(chat.get("id") or "").strip()
                },
            ),
        }
        self._write_user_payload(user_id, payload)
        self._mark_embeddings_dirty(user_id)

    def get_chat(
        self,
        *,
        user_id: str,
        conversation_id: str | None,
    ) -> dict[str, Any] | None:
        normalized_id = str(conversation_id or "").strip()
        if not normalized_id:
            return None
        for chat in self.list_chats(user_id):
            if str(chat.get("id") or "").strip() == normalized_id:
                return chat
        return None

    def conversation_history(
        self,
        *,
        user_id: str,
        conversation_id: str | None,
        limit: int = 8,
    ) -> list[dict[str, str]]:
        chat = self.get_chat(user_id=user_id, conversation_id=conversation_id)
        if chat is None:
            return []

        messages = chat.get("messages")
        if not isinstance(messages, list):
            return []

        history: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "").strip()
            text = str(message.get("text") or "").strip()
            if role not in {"user", "assistant"} or not text:
                continue
            if role == "assistant" and bool(message.get("streaming")):
                continue
            history.append({"role": role, "text": text})

        if limit > 0:
            return history[-limit:]
        return history

    def session_id(
        self,
        *,
        user_id: str,
        conversation_id: str | None,
        agent_id: str,
        mode: str,
        model_name: str | None = None,
    ) -> str | None:
        normalized_conversation_id = str(conversation_id or "").strip()
        if not normalized_conversation_id:
            return None

        payload = self._read_user_payload(user_id)
        sessions = payload.get("sessions")
        if not isinstance(sessions, dict):
            return None

        conversation_sessions = sessions.get(normalized_conversation_id)
        if not isinstance(conversation_sessions, dict):
            return None

        session_id = conversation_sessions.get(
            self._session_scope_key(
                agent_id=agent_id,
                mode=mode,
                model_name=model_name,
            )
        )
        normalized_session_id = str(session_id or "").strip()
        return normalized_session_id or None

    def save_session_id(
        self,
        *,
        user_id: str,
        conversation_id: str | None,
        agent_id: str,
        mode: str,
        model_name: str | None = None,
        session_id: str,
    ) -> None:
        normalized_conversation_id = str(conversation_id or "").strip()
        normalized_session_id = str(session_id or "").strip()
        if not normalized_conversation_id or not normalized_session_id:
            return

        payload = self._read_user_payload(user_id)
        chats = payload.get("chats")
        sessions = payload.get("sessions")
        normalized_chats = [
            self._normalize_chat(item) for item in chats if isinstance(item, dict)
        ]
        if not isinstance(sessions, dict):
            sessions = {}

        conversation_sessions = sessions.get(normalized_conversation_id)
        if not isinstance(conversation_sessions, dict):
            conversation_sessions = {}

        conversation_sessions[
            self._session_scope_key(
                agent_id=agent_id,
                mode=mode,
                model_name=model_name,
            )
        ] = normalized_session_id
        sessions[normalized_conversation_id] = conversation_sessions

        payload = {
            **{
                key: value
                for key, value in payload.items()
                if key not in {"user_id", "chats", "sessions"}
            },
            "user_id": str(user_id or "").strip() or "browser-user",
            "chats": normalized_chats,
            "sessions": sessions,
        }
        self._write_user_payload(user_id, payload)

    def _user_file(self, user_id: str) -> Path:
        normalized_user = _SAFE_USER_PATTERN.sub(
            "_",
            str(user_id or "").strip() or "browser-user",
        ).strip("._-")
        if not normalized_user:
            normalized_user = "browser-user"
        return self.root / "{user_id}.json".format(user_id=normalized_user)

    def _read_user_payload(self, user_id: str) -> dict[str, Any]:
        path = self._user_file(user_id)
        if not path.exists():
            return {"user_id": str(user_id or "").strip() or "browser-user", "chats": []}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"user_id": str(user_id or "").strip() or "browser-user", "chats": []}
        return payload if isinstance(payload, dict) else {"user_id": str(user_id or "").strip() or "browser-user", "chats": []}

    def _write_user_payload(self, user_id: str, payload: dict[str, Any]) -> None:
        path = self._user_file(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix("{suffix}.tmp".format(suffix=path.suffix))
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(path)

    def _mark_embeddings_dirty(self, user_id: str) -> None:
        try:
            from core.retrieval.index import LocalEmbeddingIndex

            LocalEmbeddingIndex(self.root.parent / ".embeddings").mark_dirty(
                "conversations",
                key=user_id,
            )
        except Exception:
            return

    def _normalize_chat(self, chat: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(chat)
        normalized.pop("sessionIds", None)
        return normalized

    def _prune_sessions(
        self,
        sessions: Any,
        conversation_ids: set[str],
    ) -> dict[str, dict[str, str]]:
        if not isinstance(sessions, dict):
            return {}

        pruned: dict[str, dict[str, str]] = {}
        for conversation_id, scoped_sessions in sessions.items():
            normalized_conversation_id = str(conversation_id or "").strip()
            if (
                not normalized_conversation_id
                or normalized_conversation_id not in conversation_ids
                or not isinstance(scoped_sessions, dict)
            ):
                continue

            normalized_scoped_sessions = {
                str(scope or "").strip(): str(session_id or "").strip()
                for scope, session_id in scoped_sessions.items()
                if str(scope or "").strip() and str(session_id or "").strip()
            }
            if normalized_scoped_sessions:
                pruned[normalized_conversation_id] = normalized_scoped_sessions

        return pruned

    def _session_scope_key(
        self,
        *,
        agent_id: str,
        mode: str,
        model_name: str | None = None,
    ) -> str:
        normalized_agent_id = str(agent_id or "").strip() or "__default_agent__"
        normalized_mode = str(mode or "").strip() or "direct"
        normalized_model_name = str(model_name or "").strip() or "__default_model__"
        return "{agent_id}::{mode}::{model_name}".format(
            agent_id=normalized_agent_id,
            mode=normalized_mode,
            model_name=normalized_model_name,
        )
