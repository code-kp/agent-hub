import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from services.conversations import ConversationStore


class ConversationStoreTest(unittest.TestCase):
    def test_save_chats_strips_client_session_ids_and_preserves_server_sessions(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            store = ConversationStore(Path(temp_dir))
            store.save_session_id(
                user_id="browser-user",
                conversation_id="chat-1",
                agent_id="web.answer",
                mode="direct",
                model_name=None,
                session_id="server-session-1",
            )

            store.save_chats(
                "browser-user",
                [
                    {
                        "id": "chat-1",
                        "title": "Chat 1",
                        "sessionIds": {"browser-user::web.answer::direct": "ui-session"},
                        "messages": [],
                    }
                ],
            )

            chats = store.list_chats("browser-user")
            self.assertEqual(len(chats), 1)
            self.assertNotIn("sessionIds", chats[0])
            self.assertEqual(
                store.session_id(
                    user_id="browser-user",
                    conversation_id="chat-1",
                    agent_id="web.answer",
                    mode="direct",
                    model_name=None,
                ),
                "server-session-1",
            )

            store.save_chats("browser-user", [])
            self.assertIsNone(
                store.session_id(
                    user_id="browser-user",
                    conversation_id="chat-1",
                    agent_id="web.answer",
                    mode="direct",
                    model_name=None,
                )
            )


if __name__ == "__main__":
    unittest.main()
