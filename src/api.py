"""
Tests:
- tests/test_api.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Tuple

from core.platform import AgentPlatform


ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = ROOT / "workspace"


@dataclass(frozen=True)
class ChatResult:
    agent_id: str
    mode: str
    session_id: str
    text: str
    events: List[Dict[str, Any]]


def _parse_sse_frame(frame: str) -> Optional[Dict[str, Any]]:
    event_type = "message"
    data_lines: List[str] = []
    for raw_line in frame.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())

    if not data_lines:
        return None

    payload: Dict[str, Any]
    try:
        payload = json.loads("\n".join(data_lines))
        if not isinstance(payload, dict):
            payload = {"payload": payload}
    except json.JSONDecodeError:
        payload = {
            "message": "Failed to parse stream payload.",
            "raw": "\n".join(data_lines),
        }

    payload.setdefault("type", event_type)
    return payload


class AgentApi:
    """Programmatic entrypoint for interacting with discovered agents."""

    def __init__(self, platform: AgentPlatform) -> None:
        self.platform = platform

    def default_agent_id(self) -> str:
        return self.platform.default_agent_id

    def catalog(self) -> Dict[str, Any]:
        return self.platform.catalog()

    def list_agents(self) -> List[Dict[str, Any]]:
        return self.platform.list_agents()

    def agent_tree(self) -> List[Dict[str, Any]]:
        return self.platform.agent_tree()

    def upload_skill_markdown(
        self,
        *,
        file_name: str,
        content: str,
        uploader_id: str = "api-user",
        namespace: str = "",
    ) -> Dict[str, Any]:
        return self.platform.upload_skill_markdown(
            file_name=file_name,
            content=content,
            uploader_id=uploader_id,
            namespace=namespace,
        )

    async def stream_chat_events(
        self,
        *,
        message: str,
        agent_id: Optional[str] = None,
        mode: Optional[str] = None,
        model_name: Optional[str] = None,
        user_id: str = "api-user",
        session_id: Optional[str] = None,
        stream: bool = True,
    ) -> Tuple[str, str, str, AsyncIterator[Dict[str, Any]]]:
        (
            resolved_agent_id,
            resolved_mode,
            next_session_id,
            raw_stream,
        ) = await self.platform.stream_chat(
            agent_id=agent_id,
            mode=mode,
            model_name=model_name,
            message=message,
            user_id=user_id,
            session_id=session_id,
            stream=stream,
        )

        async def iterate_events() -> AsyncIterator[Dict[str, Any]]:
            async for frame in raw_stream:
                parsed = _parse_sse_frame(frame)
                if parsed is not None:
                    yield parsed

        return resolved_agent_id, resolved_mode, next_session_id, iterate_events()

    async def chat(
        self,
        *,
        message: str,
        agent_id: Optional[str] = None,
        mode: Optional[str] = None,
        model_name: Optional[str] = None,
        user_id: str = "api-user",
        session_id: Optional[str] = None,
        stream: bool = True,
    ) -> ChatResult:
        resolved_agent_id, resolved_mode, next_session_id, events_iter = await self.stream_chat_events(
            message=message,
            agent_id=agent_id,
            mode=mode,
            model_name=model_name,
            user_id=user_id,
            session_id=session_id,
            stream=stream,
        )

        events: List[Dict[str, Any]] = []
        partial_chunks: List[str] = []
        final_text = ""
        async for event in events_iter:
            events.append(event)
            event_type = str(event.get("type", ""))
            if event_type == "assistant_delta":
                text = event.get("text")
                if isinstance(text, str):
                    partial_chunks.append(text)
            elif event_type == "assistant_message":
                text = event.get("text")
                if isinstance(text, str):
                    final_text = text

        if not final_text:
            final_text = "".join(partial_chunks).strip()

        return ChatResult(
            agent_id=resolved_agent_id,
            mode=resolved_mode,
            session_id=next_session_id,
            text=final_text,
            events=events,
        )


def _print_agents(agents: Iterable[Dict[str, str]]) -> None:
    for item in agents:
        print(
            "{id} :: {name} :: {description}".format(
                id=item["id"],
                name=item["name"],
                description=item["description"],
            )
        )


async def _run_repl(
    api: AgentApi,
    agent_id: Optional[str],
    user_id: str,
    mode: Optional[str],
    model_name: Optional[str],
) -> None:
    selected_agent = agent_id or api.default_agent_id()
    selected_mode = mode
    selected_model_name = model_name
    session_id: Optional[str] = None

    print("Agent API REPL")
    print("Using agent:", selected_agent)
    print("Mode:", selected_mode or "default")
    print("Model:", selected_model_name or "default")
    print("Type /exit to quit, /agents to list discovered agents.")

    while True:
        try:
            message = input("you> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not message:
            continue
        if message in {"/exit", "/quit"}:
            break
        if message == "/agents":
            _print_agents(api.list_agents())
            continue
        if message.startswith("/agent "):
            next_agent = message.split(" ", 1)[1].strip()
            if next_agent:
                selected_agent = next_agent
                session_id = None
                print("Switched agent to:", selected_agent)
            continue
        if message.startswith("/mode "):
            next_mode = message.split(" ", 1)[1].strip()
            if next_mode:
                selected_mode = next_mode
                session_id = None
                print("Switched mode to:", selected_mode)
            continue
        if message.startswith("/model "):
            next_model_name = message.split(" ", 1)[1].strip()
            selected_model_name = next_model_name or None
            session_id = None
            print("Switched model to:", selected_model_name or "default")
            continue

        try:
            resolved_agent, resolved_mode, next_session_id, events = await api.stream_chat_events(
                agent_id=selected_agent,
                mode=selected_mode,
                model_name=selected_model_name,
                message=message,
                user_id=user_id,
                session_id=session_id,
            )
        except (KeyError, ValueError) as exc:
            print("error>", str(exc))
            continue

        selected_agent = resolved_agent
        selected_mode = resolved_mode
        session_id = next_session_id

        printed_inline = False
        print("agent> ", end="", flush=True)
        async for event in events:
            event_type = str(event.get("type", ""))
            if event_type == "assistant_delta":
                text = event.get("text", "")
                if isinstance(text, str):
                    printed_inline = True
                    print(text, end="", flush=True)
            elif event_type == "assistant_message":
                text = event.get("text", "")
                if isinstance(text, str) and not printed_inline:
                    print(text, end="", flush=True)
            elif event_type in {
                "tool_started",
                "tool_completed",
                "tool_log",
                "skill_context_selected",
                "tool_selection_reason",
                "run_started",
                "run_completed",
                "error",
            }:
                if printed_inline:
                    print()
                    printed_inline = False
                text = event.get("message") or json.dumps(event, ensure_ascii=True)
                print("[{event}] {text}".format(event=event_type, text=text))
        print()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent platform API entrypoint.")
    parser.add_argument(
        "--user-id", default="cli-user", help="User identifier for session tracking."
    )
    parser.add_argument("--agent-id", default=None, help="Specific agent id to use.")
    parser.add_argument(
        "--mode",
        default=None,
        help="Runtime mode to use for the selected agent (direct or orchestrated).",
    )
    parser.add_argument(
        "--model-name",
        default=None,
        help="Model name override for the request or session.",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("list", help="List discovered agents.")
    subparsers.add_parser("catalog", help="Print the full catalog JSON payload.")

    chat_parser = subparsers.add_parser(
        "chat", help="Send one message and print final response."
    )
    chat_parser.add_argument("message", help="Message to send.")

    subparsers.add_parser("repl", help="Interactive chat session.")
    return parser


async def _run_cli(args: argparse.Namespace) -> int:
    if args.command == "list":
        _print_agents(api.list_agents())
        return 0

    if args.command == "catalog":
        print(json.dumps(api.catalog(), indent=2))
        return 0

    if args.command == "chat":
        result = await api.chat(
            agent_id=args.agent_id,
            mode=args.mode,
            model_name=args.model_name,
            message=args.message,
            user_id=args.user_id,
            session_id=None,
        )
        print(result.text)
        return 0

    await _run_repl(
        api,
        agent_id=args.agent_id,
        user_id=args.user_id,
        mode=args.mode,
        model_name=args.model_name,
    )
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run_cli(args))


# Backward-compatible runtime object used by server.py.
service = AgentPlatform(workspace_root=WORKSPACE_ROOT)
api = AgentApi(service)


if __name__ == "__main__":
    raise SystemExit(main())
