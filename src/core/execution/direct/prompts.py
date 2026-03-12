from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Sequence

from google.genai import types

from core.contracts.agent import Agent
from core.contracts.execution import ExecutionConfig
from core.contracts.tools import ToolDefinition
from core.memory.context import (
    MemorySnapshot,
    format_memory_context,
    normalize_memory_messages,
)
from core.retrieval.turns import TurnContextBundle
from core.skills.resolver import ResolvedSkillContext
from core.skills.store import SkillChunk


def build_agent_instruction(
    *,
    definition: Agent,
    tool_definitions: Sequence[ToolDefinition],
    execution: ExecutionConfig,
    additional_guidance: str = "",
) -> str:
    return "\n\n".join(
        part
        for part in [
            "Agent name: {name}".format(name=definition.name),
            "Agent description: {description}".format(
                description=definition.description
            ),
            definition.system_prompt.strip(),
            additional_guidance.strip(),
            build_tool_planning_instruction(
                tool_definitions=tool_definitions,
                execution=execution,
            ),
            "Use tools when they improve accuracy and keep responses concise.",
        ]
        if part
    )


def normalize_conversation_history(
    history: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, str]]:
    return [
        {"role": item.role, "text": item.text}
        for item in normalize_memory_messages(history, limit=8, max_chars=320)
    ]


def apply_runtime_context(
    llm_request: Any,
    resolved_context: ResolvedSkillContext | TurnContextBundle,
    *,
    conversation_history: Sequence[Mapping[str, str]] | None = None,
    memory_snapshot: MemorySnapshot | None = None,
) -> None:
    config = getattr(llm_request, "config", None)
    if config is None:
        return

    turn_context = _normalize_turn_context(resolved_context)
    skill_prompt = format_skill_context(turn_context.skills)
    recalled_conversation_prompt = format_recalled_conversations(turn_context)
    memory_prompt = format_memory_context(memory_snapshot or MemorySnapshot())
    history_prompt = (
        "" if memory_prompt else format_conversation_history(conversation_history or [])
    )
    if not skill_prompt and not recalled_conversation_prompt and not history_prompt and not memory_prompt:
        return

    system_instruction = config.system_instruction or types.Content(
        role="system", parts=[]
    )
    if not isinstance(system_instruction, types.Content):
        system_instruction = types.Content(
            role="system",
            parts=[types.Part(text=str(system_instruction))],
        )
    if not system_instruction.parts:
        system_instruction.parts.append(types.Part(text=""))

    marker = "Relevant runtime context for this turn:"
    existing = system_instruction.parts[0].text or ""
    if marker in existing:
        return

    runtime_parts = ["Relevant runtime context for this turn:"]
    if memory_prompt:
        runtime_parts.append(memory_prompt)
    if history_prompt:
        runtime_parts.append(history_prompt)
    if recalled_conversation_prompt:
        runtime_parts.append(recalled_conversation_prompt)
    if skill_prompt:
        runtime_parts.append(skill_prompt)
    runtime_context = "\n\n".join(runtime_parts)
    system_instruction.parts[0].text = "{existing}\n\n{runtime_context}".format(
        existing=existing.strip(),
        runtime_context=runtime_context,
    ).strip()
    config.system_instruction = system_instruction


def format_conversation_history(history: Sequence[Mapping[str, str]]) -> str:
    normalized = normalize_conversation_history(history)
    if not normalized:
        return ""
    lines = [
        "Recent conversation history:",
        "Use this to resolve follow-up references and implied context from earlier turns.",
    ]
    for item in normalized:
        lines.append("{role}: {text}".format(role=item["role"], text=item["text"]))
    return "\n".join(lines)


def format_recalled_conversations(context: TurnContextBundle) -> str:
    if not context.recalled_conversations:
        return ""
    lines = [
        "Retrieved past conversations:",
        "Use these only for durable context that still matters to the current request.",
    ]
    for match in context.recalled_conversations:
        metadata = match.document.metadata
        title = str(metadata.get("title") or "Conversation")
        conversation_id = str(metadata.get("conversation_id") or "").strip()
        window_start = int(metadata.get("window_start") or 0)
        window_end = int(metadata.get("window_end") or 0)
        lines.append(
            "[{title}] ({conversation_id} {window_start}:{window_end})".format(
                title=title,
                conversation_id=conversation_id or "conversation",
                window_start=window_start,
                window_end=window_end,
            )
        )
        lines.append(match.document.text)
    return "\n\n".join(lines)


def format_skill_context(context: ResolvedSkillContext) -> str:
    if context.is_empty:
        return ""
    lines = [
        "Skill context:",
        "Use these summaries and excerpts only when they materially help answer the user.",
    ]
    if context.behavior:
        lines.append("Behavior skills:")
        for skill in context.behavior:
            lines.append(
                "- [{skill_id}] ({skill_class}) {title}: {summary}".format(
                    skill_id=skill.id,
                    skill_class=skill.skill_class,
                    title=skill.title,
                    summary=skill.summary,
                )
            )
    if context.knowledge:
        lines.append("Retrieved knowledge skills:")
        for skill in context.knowledge:
            lines.append(
                "- [{skill_id}] ({skill_class}) {title}: {summary}".format(
                    skill_id=skill.id,
                    skill_class=skill.skill_class,
                    title=skill.title,
                    summary=skill.summary,
                )
            )
    if context.chunks:
        lines.append("Detailed excerpts:")
        for chunk in context.chunks:
            lines.append("[{label}]".format(label=chunk.label))
            lines.append(chunk.text)
    return "\n\n".join(lines)


def build_tool_selection_reason(
    *,
    tool_name: str,
    tool_args: Dict[str, Any],
    user_message: str,
    selected_chunks: List[SkillChunk],
    model_hint: str,
    tool_descriptions: Dict[str, str],
) -> str:
    reason_parts: List[str] = []

    hint = (model_hint or "").strip()
    if hint:
        normalized_hint = " ".join(hint.split())
        if len(normalized_hint) > 220:
            normalized_hint = "{value}...".format(value=normalized_hint[:217])
        reason_parts.append("Model intent: {hint}".format(hint=normalized_hint))

    description = tool_descriptions.get(tool_name, "").strip()
    if description:
        reason_parts.append(
            "Tool capability: {description}".format(description=description)
        )

    arg_keys = sorted(str(key) for key in tool_args.keys())
    if arg_keys:
        reason_parts.append("Inputs provided: {keys}".format(keys=", ".join(arg_keys)))

    user_tokens = {
        token
        for token in re.findall(r"[a-z0-9]{3,}", user_message.lower())
        if len(token) >= 3
    }
    related_chunks = [
        chunk
        for chunk in selected_chunks
        if any(
            token
            in "{heading} {text}".format(
                heading=chunk.heading.lower(),
                text=chunk.text.lower(),
            )
            for token in user_tokens
        )
    ]
    if related_chunks:
        top_chunk = related_chunks[0]
        reason_parts.append(
            "Related skill context: {source} / {heading}".format(
                source=top_chunk.source,
                heading=top_chunk.heading,
            )
        )

    if not reason_parts:
        return "Tool was selected by the model for this turn."
    return ". ".join(part.rstrip(".") for part in reason_parts) + "."


def build_tool_planning_instruction(
    *,
    tool_definitions: Sequence[ToolDefinition],
    execution: ExecutionConfig,
) -> str:
    if not tool_definitions or not execution.include_tool_catalog:
        return ""

    lines = [
        "Tool planning guidance:",
        "Decide for yourself whether a tool is needed. Do not call a tool unless it materially improves accuracy or freshness.",
        "Start from the resolved skill context already provided for this turn.",
        "Use the smallest reliable tool sequence. One tool is enough when it answers the question cleanly.",
        "Chain tools only when each additional step adds new evidence or verification.",
        "If a tool returns guardrail_blocked=true, do not repeat that call. Reuse earlier results, choose another tool, or answer with the evidence already gathered.",
        format_execution_guardrail_instruction(execution),
        "Tool catalog:",
    ]
    for tool in tool_definitions:
        lines.extend(format_tool_catalog_entry(tool))
    return "\n".join(line for line in lines if line)


def format_tool_catalog_entry(tool: ToolDefinition) -> List[str]:
    lines = [
        "- {name} [{category}]: {description}".format(
            name=tool.name,
            category=tool.category,
            description=tool.description,
        )
    ]
    if tool.use_when:
        lines.append("  Use when: {items}".format(items="; ".join(tool.use_when)))
    if tool.avoid_when:
        lines.append("  Avoid when: {items}".format(items="; ".join(tool.avoid_when)))
    if tool.returns:
        lines.append("  Returns: {returns}".format(returns=tool.returns))
    if tool.follow_up_tools:
        lines.append(
            "  Often followed by: {tools}".format(tools=", ".join(tool.follow_up_tools))
        )
    if tool.requires_current_data:
        lines.append("  Treat this as a current-data tool.")
    return lines


def format_execution_guardrail_instruction(execution: ExecutionConfig) -> str:
    return (
        "Execution guardrails: at most {max_tool_calls} tool calls per turn, "
        "at most {max_calls_per_tool} calls per tool, and avoid immediately repeating the same call."
    ).format(
        max_tool_calls=execution.max_tool_calls,
        max_calls_per_tool=execution.max_calls_per_tool,
    )


def planning_thinking_detail(
    context: ResolvedSkillContext | TurnContextBundle,
) -> str:
    turn_context = _normalize_turn_context(context)
    if turn_context.is_empty:
        return "No extra internal guidance was selected, so the model will decide directly whether any tool is needed."
    if turn_context.recalled_conversations:
        return "Relevant guidance and a few older conversation excerpts are ready, and the model will decide whether the answer needs tools or can be completed from context."
    return "Relevant guidance is ready, and the model will decide whether the answer needs tools or can be completed from context."


def skill_context_thinking(
    context: ResolvedSkillContext | TurnContextBundle,
) -> tuple[str, str, str]:
    turn_context = _normalize_turn_context(context)
    skills = turn_context.skills
    if turn_context.is_empty:
        return (
            "Checking relevant guidance",
            "No internal guidance was needed for this question.",
            "done",
        )

    if skills.knowledge and turn_context.recalled_conversations:
        return (
            "Checking relevant guidance",
            "Pulled in a small set of relevant guidance and older conversation context for this question.",
            "done",
        )

    if skills.knowledge:
        return (
            "Checking relevant guidance",
            "Pulled in only the small set of guidance that looks useful for this question.",
            "done",
        )

    if skills.behavior and turn_context.recalled_conversations:
        return (
            "Applying behavior guidance",
            "Using the behavior guidance that shapes how this agent responds, plus a few older related conversation excerpts.",
            "done",
        )

    if skills.behavior:
        return (
            "Applying behavior guidance",
            "Using the behavior guidance that shapes how this agent responds.",
            "done",
        )

    if turn_context.recalled_conversations:
        return (
            "Recalling related conversation context",
            "Pulled in a few older conversation excerpts that look useful for this question.",
            "done",
        )

    return (
        "Checking relevant guidance",
        "Prepared the available guidance for this question.",
        "done",
    )


def _normalize_turn_context(
    context: ResolvedSkillContext | TurnContextBundle,
) -> TurnContextBundle:
    if isinstance(context, TurnContextBundle):
        return context
    return TurnContextBundle(skills=context)
