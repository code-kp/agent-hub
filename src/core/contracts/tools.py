"""
Tests:
- tests/core/contracts/test_tools.py
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Optional, Sequence, Type, Union

from core.registry import Register
from core.stream.messages import build_error_message, build_progress_message
from core.stream.progress import emit_debug_event_nowait, emit_thinking_step_nowait


_active_tool_name: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "active_tool_name",
    default=None,
)

_CAMEL_BOUNDARY_RE = re.compile(r"(?<!^)(?=[A-Z])")
DEFAULT_CORE_TOOLSET = "core"
DEFAULT_CORE_TOOLSETS = (DEFAULT_CORE_TOOLSET,)
_core_toolsets: dict[str, tuple["ToolLike", ...]] = {
    DEFAULT_CORE_TOOLSET: ("search_skills",),
}


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
        wrapped.__annotations__ = dict(getattr(handler, "__annotations__", {}))
        return wrapped


class ToolModule:
    """Class-based authoring surface for tool modules."""

    name: str = ""
    description: str = ""
    category: str = "general"
    use_when: Sequence[str] = ()
    avoid_when: Sequence[str] = ()
    returns: str = ""
    requires_current_data: bool = False
    follow_up_tools: Sequence[str] = ()

    @property
    def progress(self) -> ProgressUpdater:
        return current_progress()

    def run(
        self, *args: Any, **kwargs: Any
    ) -> Any:  # pragma: no cover - author contract
        raise NotImplementedError("ToolModule subclasses must implement run().")


ToolClass = Type[ToolModule]
ToolLike = Union[ToolDefinition, str, ToolClass]


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
        name=(name or handler.__name__).strip(),
        description=(description or inspect.getdoc(handler) or "").strip(),
        handler=handler,
        category=str(category or "general").strip() or "general",
        use_when=_normalize_tool_metadata_list(use_when),
        avoid_when=_normalize_tool_metadata_list(avoid_when),
        returns=str(returns or "").strip(),
        requires_current_data=bool(requires_current_data),
        follow_up_tools=_normalize_tool_metadata_list(follow_up_tools),
    )


def tool_from_class(tool_cls: ToolClass) -> ToolDefinition:
    if (
        not inspect.isclass(tool_cls)
        or not issubclass(tool_cls, ToolModule)
        or tool_cls is ToolModule
    ):
        raise TypeError("tool_from_class expects a ToolModule subclass.")

    instance = tool_cls()
    handler = getattr(instance, "run", None)
    if handler is None:
        raise ValueError(
            "Tool class {name} does not define run().".format(name=tool_cls.__name__)
        )

    if (
        getattr(getattr(handler, "__func__", None), "__qualname__", "")
        == ToolModule.run.__qualname__
    ):
        raise ValueError(
            "Tool class {name} must override run().".format(name=tool_cls.__name__)
        )

    description = (
        str(getattr(tool_cls, "description", "") or "").strip()
        or inspect.getdoc(tool_cls)
        or inspect.getdoc(handler)
        or ""
    )
    return create_tool(
        handler=handler,
        name=_tool_name_from_class(tool_cls),
        description=description,
        category=getattr(tool_cls, "category", "general"),
        use_when=getattr(tool_cls, "use_when", ()),
        avoid_when=getattr(tool_cls, "avoid_when", ()),
        returns=getattr(tool_cls, "returns", ""),
        requires_current_data=getattr(tool_cls, "requires_current_data", False),
        follow_up_tools=getattr(tool_cls, "follow_up_tools", ()),
    )


def register_tool(
    tool_definition: ToolDefinition, *, name: Optional[str] = None
) -> ToolDefinition:
    register_name = (name or tool_definition.name).strip()
    if not register_name:
        raise ValueError("Tool name must be non-empty.")
    Register.register(ToolDefinition, register_name, tool_definition, overwrite=True)
    return tool_definition


def register_tool_class(tool_cls: ToolClass) -> ToolClass:
    definition = tool_from_class(tool_cls)
    register_tool(definition)
    setattr(tool_cls, "__tool_definition__", definition)
    return tool_cls


def register_tools(tool_definitions: Iterable[ToolDefinition]) -> List[ToolDefinition]:
    registered: List[ToolDefinition] = []
    for item in tool_definitions:
        registered.append(register_tool(item))
    return registered


def register_core_toolset(
    name: str,
    tools: Sequence[ToolLike],
    *,
    overwrite: bool = True,
) -> tuple[ToolLike, ...]:
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise ValueError("Core toolset name must be non-empty.")
    if not overwrite and normalized_name in _core_toolsets:
        raise ValueError(
            "Core toolset already exists: {name}".format(name=normalized_name)
        )
    normalized_tools = ensure_tool_references(tools, include_core_tools=False)
    _core_toolsets[normalized_name] = normalized_tools
    return normalized_tools


def get_core_toolset(name: str) -> tuple[ToolLike, ...]:
    normalized_name = str(name or "").strip()
    return tuple(_core_toolsets.get(normalized_name, ()))


def resolve_tool(value: ToolLike) -> ToolDefinition:
    if isinstance(value, ToolDefinition):
        return value
    if isinstance(value, str):
        return Register.get(ToolDefinition, value)
    if inspect.isclass(value) and issubclass(value, ToolModule):
        return getattr(value, "__tool_definition__", tool_from_class(value))
    raise TypeError(
        "Unsupported tool reference type: {value_type}".format(
            value_type=type(value).__name__
        )
    )


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
    return [
        definition.build_callable() for definition in ensure_tools(tool_definitions)
    ]


def ensure_tools(
    value: Optional[Iterable[ToolLike]],
    *,
    include_core_tools: bool = False,
    core_toolsets: Optional[Sequence[str]] = None,
) -> List[ToolDefinition]:
    tool_references = ensure_tool_references(
        value,
        include_core_tools=include_core_tools,
        core_toolsets=core_toolsets,
    )
    resolved: List[ToolDefinition] = []
    seen = set()
    for item in tool_references:
        definition = resolve_tool(item)
        if definition.name in seen:
            continue
        seen.add(definition.name)
        resolved.append(definition)
    return resolved


def ensure_tool_references(
    value: Optional[Iterable[ToolLike]],
    *,
    include_core_tools: bool = False,
    core_toolsets: Optional[Sequence[str]] = None,
) -> tuple[ToolLike, ...]:
    tool_references: List[ToolLike] = []
    if include_core_tools:
        tool_references.extend(_resolve_core_tool_references(core_toolsets))
    tool_references.extend(list(value or ()))

    normalized: List[ToolLike] = []
    seen = set()
    for item in tool_references:
        name = tool_reference_name(item)
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(item)
    return tuple(normalized)


def tool_reference_name(value: ToolLike) -> str:
    if isinstance(value, ToolDefinition):
        return value.name.strip()
    if isinstance(value, str):
        return value.strip()
    if inspect.isclass(value) and issubclass(value, ToolModule):
        return _tool_name_from_class(value)
    raise TypeError(
        "Unsupported tool reference type: {value_type}".format(
            value_type=type(value).__name__
        )
    )


def _resolve_core_tool_references(
    core_toolsets: Optional[Sequence[str]],
) -> List[ToolLike]:
    names = list(core_toolsets or DEFAULT_CORE_TOOLSETS)
    references: List[ToolLike] = []
    for name in names:
        references.extend(get_core_toolset(name))
    return references


def _tool_name_from_class(tool_cls: ToolClass) -> str:
    explicit_name = str(getattr(tool_cls, "name", "") or "").strip()
    if explicit_name:
        return explicit_name

    class_name = tool_cls.__name__
    if class_name.endswith("Tool"):
        class_name = class_name[:-4]
    return _CAMEL_BOUNDARY_RE.sub("_", class_name).lower()


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
