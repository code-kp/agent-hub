import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import server


class ServerUploadTest(unittest.TestCase):
    def test_chat_stream_endpoint_forwards_stream_flag(self) -> None:
        client = TestClient(server.app)

        async def fake_stream():
            yield 'event: assistant_message\ndata: {"text":"done"}\n\n'

        with patch.object(
            server.service,
            "stream_chat",
            AsyncMock(return_value=("web.answer", "session-1", fake_stream())),
        ) as stream_chat:
            response = client.post(
                "/api/chat/stream",
                json={
                    "agent_id": "web.answer",
                    "message": "hello",
                    "session_id": "session-1",
                    "user_id": "browser-user",
                    "stream": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        stream_chat.assert_awaited_once_with(
            agent_id="web.answer",
            message="hello",
            user_id="browser-user",
            session_id="session-1",
            history=None,
            stream=False,
        )
        self.assertEqual(response.headers["x-session-id"], "session-1")

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
                    "instructions": "Generate a concise title.",
                    "message": "user: How do I reset my billing password?\nassistant: Open the billing settings page.",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "Billing Password Reset")
        execute.assert_awaited_once_with(
            agent_id="general",
            instructions="Generate a concise title.",
            message="user: How do I reset my billing password?\nassistant: Open the billing settings page.",
        )

    def test_upload_skill_endpoint_accepts_markdown_and_returns_skill_metadata(self) -> None:
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
        self.assertEqual(payload["skill"]["id"], "uploads.browser-user.billing.refund-faq")
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
