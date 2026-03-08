from __future__ import annotations

from typing import Any, Iterable, Sequence

from google.adk.agents.readonly_context import ReadonlyContext

import core.execution.orchestrated.models as orchestrated_models
import core.execution.direct.prompts as runtime_prompts


def planner_instruction(
    *,
    agent_name: str,
    system_prompt: str,
    tool_definitions: Sequence[Any],
    ctx: ReadonlyContext,
    hook_guidance: str = "",
) -> str:
    return "\n\n".join(
        part
        for part in [
            "You are the planning controller for {agent_name}.".format(agent_name=agent_name),
            "Follow this agent behavior guidance when making the plan:",
            system_prompt.strip(),
            "Create a concrete multi-step plan before execution starts.",
            "Use the smallest plan that can answer the full user request reliably.",
            "Assume one tool call is usually not enough when the request needs current information, verification, or synthesis across sources.",
            "Prefer plans with 1 to 5 steps. Each step should have a clear objective and success criteria.",
            "Do not answer the user directly. Return only structured plan data.",
            hook_guidance.strip(),
            tool_catalog_block(tool_definitions),
            current_user_block(ctx),
        ]
        if part
    )


def executor_instruction(
    *,
    agent_name: str,
    system_prompt: str,
    tool_definitions: Sequence[Any],
    ctx: ReadonlyContext,
    hook_guidance: str = "",
) -> str:
    state = ctx.state
    current_step = state.get("orchestrated:current_step") or {}
    completed = state.get("orchestrated:evidence") or []

    lines = [
        "You are the execution agent for {agent_name}.".format(agent_name=agent_name),
        "Follow this agent behavior guidance while executing the current step:",
        system_prompt.strip(),
        "Execute only the current plan step.",
        "Use tools when needed to complete the step objective.",
        "Do not write the final answer to the user yet.",
        "Return a concise findings note for this step, including the key evidence gathered.",
        hook_guidance.strip(),
        tool_catalog_block(tool_definitions),
        current_user_block(ctx),
    ]
    if current_step:
        lines.extend(
            [
                "Current step:",
                "- Title: {value}".format(value=current_step.get("title", "")),
                "- Objective: {value}".format(value=current_step.get("objective", "")),
                "- Success criteria: {value}".format(value=current_step.get("success_criteria", "")),
            ]
        )
    if completed:
        lines.append("Completed step findings so far:")
        for item in completed[-4:]:
            lines.append(
                "- {title}: {summary}".format(
                    title=str(item.get("title") or "Step"),
                    summary=str(item.get("summary") or "").strip(),
                )
            )
    return "\n".join(line for line in lines if line)


def replanner_instruction(
    *,
    agent_name: str,
    system_prompt: str,
    ctx: ReadonlyContext,
    hook_guidance: str = "",
) -> str:
    state = ctx.state
    current_plan = orchestrated_models.serialize_plan(state.get("orchestrated:plan"))
    evidence = state.get("orchestrated:evidence") or []
    current_step = state.get("orchestrated:last_step") or {}

    lines = [
        "You are the replanning controller for {agent_name}.".format(agent_name=agent_name),
        "Follow this agent behavior guidance when deciding what to do next:",
        system_prompt.strip(),
        "Decide whether the workflow should continue with the remaining plan, replan, or finalize for verification.",
        "Choose finalize only if the user request appears fully answered with enough evidence.",
        "If replanning, return only the remaining work that still needs to happen. Do not repeat steps that are already completed.",
        "Return only structured decision data.",
        hook_guidance.strip(),
        current_user_block(ctx),
    ]
    if current_plan:
        lines.append("Current plan:")
        lines.append(str(current_plan))
    if current_step:
        lines.append("Most recent completed step:")
        lines.append(str(current_step))
    if evidence:
        lines.append("Evidence gathered so far:")
        for item in evidence[-6:]:
            lines.append(
                "- {title}: {summary}".format(
                    title=str(item.get("title") or "Step"),
                    summary=str(item.get("summary") or "").strip(),
                )
            )
    return "\n".join(line for line in lines if line)


def verifier_instruction(
    *,
    agent_name: str,
    system_prompt: str,
    ctx: ReadonlyContext,
    hook_guidance: str = "",
) -> str:
    state = ctx.state
    current_plan = orchestrated_models.serialize_plan(state.get("orchestrated:plan"))
    evidence = state.get("orchestrated:evidence") or []

    lines = [
        "You are the final verifier for {agent_name}.".format(agent_name=agent_name),
        "Follow this agent behavior guidance when producing the final answer:",
        system_prompt.strip(),
        "Decide whether the gathered evidence is enough to answer the user completely and accurately.",
        "If ready, produce the final user-facing answer.",
        "If not ready, set ready=false and explain what is still missing.",
        "Return only structured verification data.",
        hook_guidance.strip(),
        current_user_block(ctx),
    ]
    if current_plan:
        lines.append("Current plan:")
        lines.append(str(current_plan))
    if evidence:
        lines.append("Evidence gathered so far:")
        for item in evidence[-8:]:
            lines.append(
                "- {title}: {summary}".format(
                    title=str(item.get("title") or "Step"),
                    summary=str(item.get("summary") or "").strip(),
                )
            )
    return "\n".join(line for line in lines if line)


def summarize_plan(plan: orchestrated_models.Plan | dict[str, Any]) -> str:
    if isinstance(plan, dict):
        plan = orchestrated_models.Plan.model_validate(plan)

    if not plan.steps:
        return "Created a minimal plan with no explicit tool steps."

    rendered_steps = []
    for index, step in enumerate(plan.steps, start=1):
        rendered_steps.append("{index}. {title}".format(index=index, title=step.title))
    return "Created a {count}-step plan: {steps}.".format(
        count=len(plan.steps),
        steps=" ".join(rendered_steps),
    )


def summarize_evidence(items: Iterable[dict[str, Any]]) -> str:
    recent = list(items)[-4:]
    if not recent:
        return "No step findings were recorded."
    return " | ".join(
        "{title}: {summary}".format(
            title=str(item.get("title") or "Step"),
            summary=str(item.get("summary") or "").strip(),
        )
        for item in recent
    )


def tool_catalog_block(tool_definitions: Sequence[Any]) -> str:
    if not tool_definitions:
        return ""

    lines = ["Available tools:"]
    for tool in tool_definitions:
        lines.extend(runtime_prompts.format_tool_catalog_entry(tool))
    return "\n".join(lines)


def current_user_block(ctx: ReadonlyContext) -> str:
    user_text = ""
    user_content = getattr(ctx, "user_content", None)
    if user_content and getattr(user_content, "parts", None):
        user_text = "".join(part.text for part in user_content.parts if getattr(part, "text", None))
    return "Current user request:\n{message}".format(message=user_text.strip())
