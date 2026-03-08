import asyncio
import time
import unittest

from core.contracts.tools import create_tool, current_progress
from core.stream.progress import (
    EventStream,
    bind_progress_stream,
    reset_progress_stream,
)


class LiveProgressTest(unittest.IsolatedAsyncioTestCase):
    async def test_emit_nowait_from_worker_thread_reaches_stream(self) -> None:
        stream = EventStream()

        def worker() -> None:
            stream.emit_nowait("tool_log", {"message": "worker update"})

        await asyncio.to_thread(worker)

        event = await asyncio.wait_for(stream.queue.get(), timeout=1)
        self.assertEqual(event["type"], "tool_log")
        self.assertEqual(event["message"], "worker update")

    async def test_sync_tool_progress_arrives_before_tool_finishes(self) -> None:
        stream = EventStream()
        stream_token = bind_progress_stream(stream)

        def slow_tool() -> dict:
            progress = current_progress()
            progress.comment("Started collecting information.")
            time.sleep(0.2)
            progress.comment("Still working through the request.")
            time.sleep(0.2)
            return {"ok": True}

        tool = create_tool(
            slow_tool,
            name="slow_tool",
            description="Slow test tool.",
        )

        try:
            task = asyncio.create_task(tool.build_callable()())

            first_event = await asyncio.wait_for(stream.queue.get(), timeout=1)
            self.assertEqual(first_event["type"], "thinking_step")
            self.assertEqual(first_event["label"], "Started collecting information.")
            self.assertEqual(first_event["state"], "running")
            self.assertFalse(
                task.done(), "progress should arrive before the tool completes"
            )

            result = await asyncio.wait_for(task, timeout=2)
            self.assertEqual(result, {"ok": True})
        finally:
            reset_progress_stream(stream_token)


if __name__ == "__main__":
    unittest.main()
