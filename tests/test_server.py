import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import core.contracts.models as contract_models
import server
from services.conversations import ConversationStore


class ServerUploadTest(unittest.TestCase):
    def test_models_endpoint_returns_catalog(self) -> None:
        client = TestClient(server.app)

        with patch.object(
            server.service,
            "list_available_models",
            return_value={"models": [{"id": "mdl_demo", "hash": "demo", "label": "Gemini Demo"}]},
        ) as list_models:
            response = client.get("/api/models")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"][0]["id"], "mdl_demo")
        list_models.assert_called_once_with()

    def test_chat_stream_endpoint_forwards_stream_flag(self) -> None:
        client = TestClient(server.app)

        async def fake_stream():
            yield 'event: assistant_message\ndata: {"text":"done"}\n\n'

        with patch.object(
            server.service,
            "stream_chat",
            AsyncMock(
                return_value=("web.answer", "orchestrated", "session-1", fake_stream())
            ),
        ) as stream_chat:
            response = client.post(
                "/api/chat/stream",
                json={
                    "agent_id": "web.answer",
                    "mode": "orchestrated",
                    "model_name": "gemini-2.0-flash",
                    "message": "hello",
                    "session_id": "session-1",
                    "user_id": "browser-user",
                    "stream": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        stream_chat.assert_awaited_once_with(
            agent_id="web.answer",
            mode="orchestrated",
            model_name="gemini-2.0-flash",
            message="hello",
            user_id="browser-user",
            session_id="session-1",
            history=None,
            stream=False,
        )
        self.assertEqual(response.headers["x-session-id"], "session-1")
        self.assertEqual(response.headers["x-mode"], "orchestrated")

    def test_chat_stream_endpoint_accepts_model_id(self) -> None:
        client = TestClient(server.app)
        selected = contract_models.available_models()[0]

        async def fake_stream():
            yield 'event: assistant_message\ndata: {"text":"done"}\n\n'

        with patch.object(
            server.service,
            "resolve_model_name",
            return_value=selected.model_name,
        ) as resolve_model_name:
            with patch.object(
                server.service,
                "stream_chat",
                AsyncMock(
                    return_value=("web.answer", "direct", "session-2", fake_stream())
                ),
            ) as stream_chat:
                response = client.post(
                    "/api/chat/stream",
                    json={
                        "agent_id": "web.answer",
                        "model_id": selected.id,
                        "message": "hello",
                    },
                )

        self.assertEqual(response.status_code, 200)
        resolve_model_name.assert_called_once_with(
            model_id=selected.id,
            model_name=None,
        )
        stream_chat.assert_awaited_once_with(
            agent_id="web.answer",
            mode=None,
            model_name=selected.model_name,
            message="hello",
            user_id="browser-user",
            session_id=None,
            history=None,
            stream=True,
        )

    def test_conversation_session_endpoint_returns_server_side_session(
        self,
    ) -> None:
        client = TestClient(server.app)

        with TemporaryDirectory() as temp_dir:
            store = ConversationStore(Path(temp_dir))
            store.save_chats(
                "browser-user",
                [
                    {
                        "id": "chat-1",
                        "agentId": "web.answer",
                        "messages": [],
                    }
                ],
            )
            store.save_session_id(
                user_id="browser-user",
                conversation_id="chat-1",
                agent_id="web.answer",
                mode="direct",
                model_name="gemini-2.0-flash",
                session_id="session-1",
            )

            original_store = server.conversation_store
            server.conversation_store = store
            try:
                with patch.object(
                    server.service,
                    "resolve_model_name",
                    return_value="gemini-2.0-flash",
                ) as resolve_model_name:
                    with patch.object(
                        server.platform_service,
                        "resolve_runtime",
                        return_value=("web.answer", "direct", object()),
                    ) as resolve_runtime:
                        response = client.get(
                            "/api/conversations/session",
                            params={
                                "user_id": "browser-user",
                                "conversation_id": "chat-1",
                                "agent_id": "web.answer",
                                "mode": "direct",
                                "model_name": "gemini-2.0-flash",
                            },
                        )
            finally:
                server.conversation_store = original_store

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["session_id"], "session-1")
            resolve_model_name.assert_called_once_with(
                model_id=None,
                model_name="gemini-2.0-flash",
            )
            resolve_runtime.assert_called_once_with(
                "web.answer",
                mode="direct",
                model_name="gemini-2.0-flash",
            )

    def test_chat_stream_endpoint_reuses_server_side_session_for_conversation(
        self,
    ) -> None:
        client = TestClient(server.app)

        async def fake_stream():
            yield 'event: assistant_message\ndata: {"text":"done"}\n\n'

        with TemporaryDirectory() as temp_dir:
            store = ConversationStore(Path(temp_dir))
            store.save_chats(
                "browser-user",
                [
                    {
                        "id": "chat-1",
                        "agentId": "web.answer",
                        "messages": [
                            {"role": "user", "text": "Earlier question"},
                            {"role": "assistant", "text": "Earlier answer"},
                        ],
                    }
                ],
            )
            store.save_session_id(
                user_id="browser-user",
                conversation_id="chat-1",
                agent_id="web.answer",
                mode="orchestrated",
                model_name="gemini-2.0-flash",
                session_id="session-1",
            )

            original_store = server.conversation_store
            server.conversation_store = store
            try:
                with patch.object(
                    server.service,
                    "resolve_model_name",
                    return_value="gemini-2.0-flash",
                ) as resolve_model_name:
                    with patch.object(
                        server.platform_service,
                        "resolve_runtime",
                        return_value=("web.answer", "orchestrated", object()),
                    ) as resolve_runtime:
                        with patch.object(
                            server.service,
                            "stream_chat",
                            AsyncMock(
                                return_value=(
                                    "web.answer",
                                    "orchestrated",
                                    "session-2",
                                    fake_stream(),
                                )
                            ),
                        ) as stream_chat:
                            response = client.post(
                                "/api/chat/stream",
                                json={
                                    "agent_id": "web.answer",
                                    "mode": "orchestrated",
                                    "model_name": "gemini-2.0-flash",
                                    "conversation_id": "chat-1",
                                    "message": "hello",
                                },
                            )
            finally:
                server.conversation_store = original_store

            self.assertEqual(response.status_code, 200)
            resolve_model_name.assert_called_once_with(
                model_id=None,
                model_name="gemini-2.0-flash",
            )
            resolve_runtime.assert_called_once_with(
                "web.answer",
                mode="orchestrated",
                model_name="gemini-2.0-flash",
            )
            stream_chat.assert_awaited_once_with(
                agent_id="web.answer",
                mode="orchestrated",
                model_name="gemini-2.0-flash",
                message="hello",
                user_id="browser-user",
                session_id="session-1",
                history=[
                    {"role": "user", "text": "Earlier question"},
                    {"role": "assistant", "text": "Earlier answer"},
                ],
                stream=True,
            )
            self.assertEqual(response.headers["x-session-id"], "session-2")
            self.assertEqual(
                store.session_id(
                    user_id="browser-user",
                    conversation_id="chat-1",
                    agent_id="web.answer",
                    mode="orchestrated",
                    model_name="gemini-2.0-flash",
                ),
                "session-2",
            )

    def test_ai_endpoint_routes_conversation_title_task(self) -> None:
        client = TestClient(server.app)

        with patch.object(
            server.ai_service,
            "generate_text",
            AsyncMock(return_value="Billing Password Reset"),
        ) as execute:
            response = client.post(
                "/api/ai",
                json={
                    "agent_id": "general",
                    "model_name": "gemini-2.0-flash",
                    "instructions": "Generate a concise title.",
                    "message": "user: How do I reset my billing password?\nassistant: Open the billing settings page.",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "Billing Password Reset")
        execute.assert_awaited_once_with(
            agent_id="general",
            model_name="gemini-2.0-flash",
            instructions="Generate a concise title.",
            message="user: How do I reset my billing password?\nassistant: Open the billing settings page.",
        )

    def test_upload_skill_endpoint_accepts_markdown_and_returns_skill_metadata(
        self,
    ) -> None:
        client = TestClient(server.app)

        with patch.object(server.service, "upload_skill_markdown") as upload_skill:
            upload_skill.return_value = {
                "id": "uploads.browser-user.billing.refund-faq",
                "source": "uploads/browser-user/billing/refund-faq.md",
                "path": "/tmp/uploads/browser-user/billing/refund-faq.md",
                "title": "Refund FAQ",
                "class": "knowledge",
                "summary": "Refund policy details.",
            }

            response = client.post(
                "/api/skills/upload",
                data={
                    "user_id": "browser-user",
                    "namespace": "billing",
                },
                files={
                    "file": (
                        "refund-faq.md",
                        b"# Refund FAQ\n\nRefunds are available within 30 days.\n",
                        "text/markdown",
                    )
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["skill"]["id"], "uploads.browser-user.billing.refund-faq"
        )
        self.assertEqual(payload["skill"]["class"], "knowledge")
        self.assertIn("note", payload["usage"])

    def test_upload_skill_endpoint_rejects_non_markdown_files(self) -> None:
        client = TestClient(server.app)
        response = client.post(
            "/api/skills/upload",
            files={
                "file": (
                    "notes.txt",
                    b"plain text",
                    "text/plain",
                )
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Only markdown", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
