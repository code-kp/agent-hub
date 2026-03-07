from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Optional, Sequence, Union

from core.stream.messages import build_error_message, build_progress_message
from core.stream.progress import emit_debug_event_nowait, emit_thinking_step_nowait
from core.registry import Register


_active_tool_name: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "active_tool_name",
    default=None,
)


class ProgressUpdater:
    """Utility available inside tool handlers for live UI comments."""

    def __init__(self, tool_name: Optional[str]) -> None:
        self.tool_name = tool_name or "tool"

    def think(
        self,
        label: str,
        *,
        detail: str = "",
        step_id: Optional[str] = None,
        state: str = "running",
        **payload: Any,
    ) -> None:
        emit_thinking_step_nowait(
            step_id=step_id or self.tool_name,
            label=label,
            detail=detail,
            state=state,
            tool_name=self.tool_name,
            **payload,
        )

    def debug(self, message: str, **payload: Any) -> None:
        body = {
            "tool_name": self.tool_name,
            "message": build_progress_message(message, **payload),
        }
        body.update(payload)
        emit_debug_event_nowait("tool_log", **body)

    def comment(self, message: str, **payload: Any) -> None:
        self.think(message, **payload)


def current_progress() -> ProgressUpdater:
    return ProgressUpdater(_active_tool_name.get())


@dataclass(frozen=True)
class ToolDefinition:
    """Declarative tool definition used by agent modules."""

    name: str
    description: str
    handler: Callable[..., Any]
    category: str = "general"
    use_when: tuple[str, ...] = ()
    avoid_when: tuple[str, ...] = ()
    returns: str = ""
    requires_current_data: bool = False
    follow_up_tools: tuple[str, ...] = ()

    def build_callable(self) -> Callable[..., Any]:
        handler = self.handler

        @functools.wraps(handler)
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            token = _active_tool_name.set(self.name)
            try:
                if inspect.iscoroutinefunction(handler):
                    result = await handler(*args, **kwargs)
                else:
                    result = await asyncio.to_thread(handler, *args, **kwargs)
                return result
            except Exception as exc:
                emit_debug_event_nowait(
                    "tool_log",
                    tool_name=self.name,
                    message=build_error_message(str(exc)),
                    error=str(exc),
                )
                raise
            finally:
                _active_tool_name.reset(token)

        wrapped.__name__ = self.name
        wrapped.__doc__ = self.description or handler.__doc__
        wrapped.__signature__ = inspect.signature(handler)  # type: ignore[attr-defined]
        return wrapped


def create_tool(
    handler: Callable[..., Any],
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: str = "general",
    use_when: Optional[Sequence[str]] = None,
    avoid_when: Optional[Sequence[str]] = None,
    returns: str = "",
    requires_current_data: bool = False,
    follow_up_tools: Optional[Sequence[str]] = None,
) -> ToolDefinition:
    return ToolDefinition(
        name=name or handler.__name__,
        description=(description or inspect.getdoc(handler) or "").strip(),
        handler=handler,
        category=str(category or "general").strip() or "general",
        use_when=_normalize_tool_metadata_list(use_when),
        avoid_when=_normalize_tool_metadata_list(avoid_when),
        returns=str(returns or "").strip(),
        requires_current_data=bool(requires_current_data),
        follow_up_tools=_normalize_tool_metadata_list(follow_up_tools),
    )


ToolLike = Union[ToolDefinition, str]


def register_tool(tool_definition: ToolDefinition, *, name: Optional[str] = None) -> ToolDefinition:
    register_name = (name or tool_definition.name).strip()
    if not register_name:
        raise ValueError("Tool name must be non-empty.")
    Register.register(ToolDefinition, register_name, tool_definition, overwrite=True)
    return tool_definition


def register_tools(tool_definitions: Iterable[ToolDefinition]) -> List[ToolDefinition]:
    registered: List[ToolDefinition] = []
    for item in tool_definitions:
        registered.append(register_tool(item))
    return registered


def resolve_tool(value: ToolLike) -> ToolDefinition:
    if isinstance(value, ToolDefinition):
        return value
    if isinstance(value, str):
        return Register.get(ToolDefinition, value)
    raise TypeError("Unsupported tool reference type: {value_type}".format(value_type=type(value).__name__))


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: str = "general",
    use_when: Optional[Sequence[str]] = None,
    avoid_when: Optional[Sequence[str]] = None,
    returns: str = "",
    requires_current_data: bool = False,
    follow_up_tools: Optional[Sequence[str]] = None,
    register: bool = True,
):
    def decorator(handler: Callable[..., Any]) -> ToolDefinition:
        definition = create_tool(
            handler=handler,
            name=name,
            description=description,
            category=category,
            use_when=use_when,
            avoid_when=avoid_when,
            returns=returns,
            requires_current_data=requires_current_data,
            follow_up_tools=follow_up_tools,
        )
        if register:
            register_tool(definition)
        return definition

    return decorator


def build_adk_tools(tool_definitions: Sequence[ToolLike]) -> List[Callable[..., Any]]:
    return [definition.build_callable() for definition in ensure_tools(tool_definitions)]


def ensure_tools(value: Optional[Iterable[ToolLike]]) -> List[ToolDefinition]:
    return [resolve_tool(item) for item in list(value or [])]


def _normalize_tool_metadata_list(values: Optional[Sequence[str]]) -> tuple[str, ...]:
    normalized = []
    seen = set()
    for raw in list(values or ()):
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(normalized)
