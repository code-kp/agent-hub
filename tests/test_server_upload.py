import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import server


class ServerUploadTest(unittest.TestCase):
    def test_upload_skill_endpoint_accepts_markdown_and_returns_skill_metadata(self) -> None:
        client = TestClient(server.app)

        with patch.object(server.service, "upload_skill_markdown") as upload_skill:
            upload_skill.return_value = {
                "id": "uploads.browser-user.billing.refund-faq",
                "source": "uploads/browser-user/billing/refund-faq.md",
                "path": "/tmp/uploads/browser-user/billing/refund-faq.md",
                "title": "Refund FAQ",
                "type": "knowledge",
                "mode": "auto",
                "summary": "Refund policy details.",
                "tags": ["uploaded", "browser-user", "billing"],
                "triggers": ["refund"],
                "priority": 60,
            }

            response = client.post(
                "/api/skills/upload",
                data={
                    "user_id": "browser-user",
                    "namespace": "billing",
                    "tags": "billing,refund",
                    "triggers": "refund",
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
        self.assertEqual(payload["skill"]["type"], "knowledge")
        self.assertIn("recommended_type", payload["usage"])

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
