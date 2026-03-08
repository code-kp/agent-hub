import types as py_types
import unittest

from google.adk.events import Event
from google.genai import types

import core.contracts.hooks as contracts_hooks
import core.execution.orchestrated.controller as orchestrated_controller


class _FinalizeHook(contracts_hooks.AgentHooks):
    def finalize_response(self, *, text: str, state: contracts_hooks.HookState) -> str:
        return "[final]{text}".format(text=text)


class _WriterAgentStub:
    name = "writer-agent"

    async def run_async(self, ctx):
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            partial=True,
            content=types.Content(role="model", parts=[types.Part(text="Hello ")]),
        )
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            turn_complete=True,
            content=types.Content(role="model", parts=[types.Part(text="world")]),
        )


class OrchestratedWriterTest(unittest.IsolatedAsyncioTestCase):
    async def test_stream_writer_relays_partial_and_final_events(self) -> None:
        controller = orchestrated_controller.OrchestratedController.model_construct(
            name="controller",
            writer_agent=_WriterAgentStub(),
            agent_hooks=_FinalizeHook(),
        )

        ctx = py_types.SimpleNamespace(
            invocation_id="inv-1",
            session=py_types.SimpleNamespace(
                state={orchestrated_controller.HOOK_STATE_KEY: {}},
                user_id="user-1",
                id="session-1",
            ),
            user_content=None,
        )

        events = []
        async for event in controller._stream_writer(ctx):
            events.append(event)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].author, "controller")
        self.assertTrue(getattr(events[0], "partial", False))
        self.assertEqual(_event_text(events[0]), "Hello ")

        self.assertEqual(events[1].author, "controller")
        self.assertTrue(events[1].is_final_response())
        self.assertEqual(_event_text(events[1]), "[final]Hello world")


def _event_text(event: Event) -> str:
    if not event.content or not event.content.parts:
        return ""
    return "".join(
        part.text for part in event.content.parts if getattr(part, "text", None)
    )


if __name__ == "__main__":
    unittest.main()
