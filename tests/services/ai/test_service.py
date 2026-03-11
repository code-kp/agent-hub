import unittest
from unittest import mock

from services.ai import AiService, AiServiceError
import services.ai.service as ai_service


class AiServiceTest(unittest.IsolatedAsyncioTestCase):
    def test_build_ui_agent_identifier_sanitizes_input(self) -> None:
        identifier = ai_service.build_ui_agent_identifier("support.triage 2026")

        self.assertEqual(identifier, "support_triage_2026_ui_request")

    async def test_generate_text_rejects_blank_instructions(self) -> None:
        service = AiService(mock.Mock())

        with self.assertRaises(AiServiceError):
            await service.generate_text(
                agent_id="general",
                instructions="",
                message="hello",
            )

    async def test_generate_text_rejects_blank_message(self) -> None:
        service = AiService(mock.Mock())

        with self.assertRaises(AiServiceError):
            await service.generate_text(
                agent_id="general",
                instructions="do something",
                message="",
            )

    async def test_generate_text_uses_adk_runner(self) -> None:
        runtime = mock.Mock(model_name="gemini-2.0-flash")
        platform = mock.Mock()
        platform.resolve_runtime.return_value = ("general", "direct", runtime)
        service = AiService(platform)

        async def fake_events():
            event = mock.Mock()
            event.partial = False
            event.is_final_response.return_value = True
            yield event

        with mock.patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}, clear=False):
            with mock.patch(
                "services.ai.service.shared_adk.create_llm_agent",
                return_value=mock.Mock(),
            ) as create_agent:
                with mock.patch(
                    "services.ai.service.shared_adk.create_runner",
                    return_value=mock.Mock(),
                ) as create_runner:
                    with mock.patch(
                        "services.ai.service.shared_adk.stream_runner_events",
                        return_value=fake_events(),
                    ):
                        with mock.patch(
                            "services.ai.service.shared_adk.extract_text",
                            return_value="Billing Password Reset",
                        ):
                            result = await service.generate_text(
                                agent_id="general",
                                model_name="gemini-2.0-flash",
                                instructions="Generate a title.",
                                message="user: how do I reset billing password?",
                            )

        create_agent.assert_called_once()
        create_runner.assert_called_once()
        platform.resolve_runtime.assert_called_once_with(
            "general",
            model_name="gemini-2.0-flash",
        )
        self.assertEqual(result, "Billing Password Reset")

    async def test_generate_text_rejects_missing_key(self) -> None:
        service = AiService(mock.Mock())

        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(AiServiceError):
                await service.generate_text(
                    agent_id="general",
                    instructions="Generate a title.",
                    message="user: hello",
                )


if __name__ == "__main__":
    unittest.main()
