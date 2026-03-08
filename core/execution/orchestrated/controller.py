from __future__ import annotations

from contextlib import aclosing
from typing import Any, Callable, Optional, Sequence

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.agents.readonly_context import ReadonlyContext
from google.genai import types

import core.contracts.execution as contracts_execution
import core.contracts.hooks as contracts_hooks
import core.execution.orchestrated.models as orchestrated_models
import core.execution.orchestrated.prompts as orchestrated_prompts


PLANNER_OUTPUT_KEY = "orchestrated:planner_output"
REPLANNER_OUTPUT_KEY = "orchestrated:replanner_output"
VERIFIER_OUTPUT_KEY = "orchestrated:verifier_output"
PLAN_STATE_KEY = "orchestrated:plan"
CURRENT_STEP_STATE_KEY = "orchestrated:current_step"
LAST_STEP_STATE_KEY = "orchestrated:last_step"
EVIDENCE_STATE_KEY = "orchestrated:evidence"
VERIFICATION_STATE_KEY = "orchestrated:verification"
COMPLETED_STEP_IDS_STATE_KEY = "orchestrated:completed_step_ids"
HOOK_STATE_KEY = "orchestrated:hook_state"


class OrchestratedController(BaseAgent):
    planner_agent: LlmAgent
    executor_agent: LlmAgent
    replanner_agent: LlmAgent
    verifier_agent: LlmAgent
    writer_agent: LlmAgent
    execution_config: contracts_execution.ExecutionConfig
    agent_hooks: contracts_hooks.AgentHooks

    async def _run_async_impl(self, ctx: InvocationContext):
        self._initialize_run_state(ctx)

        yield self._thinking_event(
            ctx,
            step_id="plan",
            label="Creating the plan",
            detail="Breaking the request into concrete steps before any tools are run.",
            state="running",
        )
        plan_capture: dict[str, Any] = {}
        async for event in self._relay_agent(
            ctx,
            self.planner_agent,
            capture=plan_capture,
            output_key=PLANNER_OUTPUT_KEY,
        ):
            yield event
        plan_payload = plan_capture.get("output")
        plan = (
            self._default_plan(ctx)
            if not plan_payload
            else orchestrated_models.Plan.model_validate(plan_payload)
        )
        self._set_plan(ctx, plan)
        yield self._thinking_event(
            ctx,
            step_id="plan",
            label="Plan ready",
            detail=orchestrated_prompts.summarize_plan(plan),
            state="done",
        )

        replan_count = 0
        verification_rounds = 0

        while True:
            next_step = self._next_pending_step(ctx)
            if next_step is None:
                verification_rounds += 1
                verification_capture: dict[str, Any] = {}
                async for event in self._relay_agent(
                    ctx,
                    self.verifier_agent,
                    capture=verification_capture,
                    output_key=VERIFIER_OUTPUT_KEY,
                ):
                    yield event
                verification_payload = verification_capture.get("output")
                verification = (
                    orchestrated_models.Verification(
                        ready=False,
                        rationale="No verifier output was returned.",
                        answer="",
                    )
                    if not verification_payload
                    else orchestrated_models.Verification.model_validate(
                        verification_payload
                    )
                )
                ctx.session.state[VERIFICATION_STATE_KEY] = verification.model_dump(
                    exclude_none=True
                )
                if verification.ready:
                    yield self._thinking_event(
                        ctx,
                        step_id="verify",
                        label="Answer verified",
                        detail=verification.rationale,
                        state="done",
                    )
                    yield self._thinking_event(
                        ctx,
                        step_id="answer",
                        label="Writing the answer",
                        detail="Turning the verified evidence into the final response.",
                        state="running",
                    )
                    async for event in self._stream_writer(ctx):
                        yield event
                    return

                if (
                    replan_count >= self.execution_config.max_replans
                    or verification_rounds
                    >= self.execution_config.max_verification_rounds
                ):
                    fallback = self._fallback_answer(verification)
                    yield self._thinking_event(
                        ctx,
                        step_id="verify",
                        label="Answer finalized with caveat",
                        detail=verification.rationale,
                        state="done",
                    )
                    yield self._final_answer_event(ctx, fallback)
                    return

                yield self._thinking_event(
                    ctx,
                    step_id="replan",
                    label="Revising the plan",
                    detail="The current evidence is not enough yet, so the remaining work is being adjusted.",
                    state="running",
                )
                decision_capture: dict[str, Any] = {}
                async for event in self._relay_agent(
                    ctx,
                    self.replanner_agent,
                    capture=decision_capture,
                    output_key=REPLANNER_OUTPUT_KEY,
                ):
                    yield event
                decision_payload = decision_capture.get("output")
                decision = (
                    orchestrated_models.Decision(
                        action="continue",
                        rationale="No replan output was returned, so the controller is continuing with the current plan.",
                    )
                    if not decision_payload
                    else orchestrated_models.Decision.model_validate(decision_payload)
                )
                if decision.action == "replan" and decision.updated_plan:
                    replan_count += 1
                    self._set_plan(ctx, decision.updated_plan)
                    yield self._thinking_event(
                        ctx,
                        step_id="replan",
                        label="Plan revised",
                        detail=orchestrated_prompts.summarize_plan(
                            decision.updated_plan
                        ),
                        state="done",
                    )
                    continue

                yield self._final_answer_event(ctx, self._fallback_answer(verification))
                return

            self._set_current_step(ctx, next_step)
            yield self._thinking_event(
                ctx,
                step_id="execute",
                label="Executing the next step",
                detail="{title}: {objective}".format(
                    title=next_step.title,
                    objective=next_step.objective,
                ),
                state="running",
            )

            executor_capture: dict[str, Any] = {"text": ""}
            async for event in self._relay_agent(
                ctx,
                self.executor_agent,
                capture=executor_capture,
            ):
                yield event
            step_summary = (
                str(executor_capture.get("text") or "").strip()
                or "Completed the step without a written findings note."
            )
            self._record_step_completion(ctx, next_step, step_summary)
            yield self._thinking_event(
                ctx,
                step_id="execute",
                label="Step completed",
                detail=step_summary,
                state="done",
            )

            if self._next_pending_step(ctx) is None:
                continue

            yield self._thinking_event(
                ctx,
                step_id="replan",
                label="Checking whether the plan still holds",
                detail="Deciding whether to continue, replan, or finalize.",
                state="running",
            )
            decision_capture: dict[str, Any] = {}
            async for event in self._relay_agent(
                ctx,
                self.replanner_agent,
                capture=decision_capture,
                output_key=REPLANNER_OUTPUT_KEY,
            ):
                yield event
            decision_payload = decision_capture.get("output")
            decision = (
                orchestrated_models.Decision(
                    action="continue",
                    rationale="No replan output was returned, so the controller is continuing with the current plan.",
                )
                if not decision_payload
                else orchestrated_models.Decision.model_validate(decision_payload)
            )
            if decision.action == "finalize":
                yield self._thinking_event(
                    ctx,
                    step_id="replan",
                    label="Plan complete",
                    detail=decision.rationale,
                    state="done",
                )
                self._mark_plan_complete(ctx)
                continue
            if (
                decision.action == "replan"
                and decision.updated_plan
                and replan_count < self.execution_config.max_replans
            ):
                replan_count += 1
                self._set_plan(ctx, decision.updated_plan)
                yield self._thinking_event(
                    ctx,
                    step_id="replan",
                    label="Plan revised",
                    detail=orchestrated_prompts.summarize_plan(decision.updated_plan),
                    state="done",
                )
                continue
            yield self._thinking_event(
                ctx,
                step_id="replan",
                label="Continuing with the current plan",
                detail=decision.rationale,
                state="done",
            )

    async def _relay_agent(
        self,
        ctx: InvocationContext,
        agent: BaseAgent,
        *,
        capture: dict[str, Any],
        output_key: Optional[str] = None,
    ):
        async with aclosing(agent.run_async(ctx)) as agen:
            async for event in agen:
                if output_key and output_key in event.actions.state_delta:
                    capture["output"] = event.actions.state_delta[output_key]
                    ctx.session.state[output_key] = capture["output"]
                if event.author == agent.name and event.is_final_response():
                    text = _event_text(event).strip()
                    if text:
                        capture["text"] = text
                hook_state = self._hook_state(ctx)
                for response in event.get_function_responses() or []:
                    self.agent_hooks.on_tool_response(
                        state=hook_state,
                        tool_name=response.name,
                        payload=response.response,
                    )
                ctx.session.state[HOOK_STATE_KEY] = hook_state
                yield event

    def _initialize_run_state(self, ctx: InvocationContext) -> None:
        ctx.session.state[PLAN_STATE_KEY] = {}
        ctx.session.state[EVIDENCE_STATE_KEY] = []
        ctx.session.state[HOOK_STATE_KEY] = self.agent_hooks.create_turn_state(
            agent_id=self.name,
            user_id=str(getattr(ctx.session, "user_id", "") or ""),
            session_id=str(
                getattr(ctx.session, "id", getattr(ctx.session, "session_id", "")) or ""
            ),
            message=_current_user_text(ctx),
        )
        ctx.session.state[CURRENT_STEP_STATE_KEY] = {}
        ctx.session.state[LAST_STEP_STATE_KEY] = {}
        ctx.session.state[VERIFICATION_STATE_KEY] = {}
        ctx.session.state[COMPLETED_STEP_IDS_STATE_KEY] = []

    def _default_plan(self, ctx: InvocationContext) -> orchestrated_models.Plan:
        return orchestrated_models.Plan(
            goal="Answer the user's request reliably.",
            done_when="There is enough evidence to answer the user directly.",
            steps=[
                orchestrated_models.PlanStep(
                    id="step_1",
                    title="Gather the required evidence",
                    objective="Use the available tools and guidance to gather enough information for the request.",
                    success_criteria="The key facts needed for the answer have been collected.",
                )
            ],
        )

    def _set_plan(self, ctx: InvocationContext, plan: orchestrated_models.Plan) -> None:
        ctx.session.state[PLAN_STATE_KEY] = plan.model_dump(exclude_none=True)
        ctx.session.state[COMPLETED_STEP_IDS_STATE_KEY] = []

    def _set_current_step(
        self, ctx: InvocationContext, step: orchestrated_models.PlanStep
    ) -> None:
        ctx.session.state[CURRENT_STEP_STATE_KEY] = step.model_dump(exclude_none=True)

    def _record_step_completion(
        self,
        ctx: InvocationContext,
        step: orchestrated_models.PlanStep,
        summary: str,
    ) -> None:
        evidence = list(ctx.session.state.get(EVIDENCE_STATE_KEY) or [])
        completed = list(ctx.session.state.get(COMPLETED_STEP_IDS_STATE_KEY) or [])
        entry = {
            "id": step.id,
            "title": step.title,
            "summary": summary,
            "success_criteria": step.success_criteria,
        }
        evidence.append(entry)
        completed.append(step.id)
        ctx.session.state[EVIDENCE_STATE_KEY] = evidence
        ctx.session.state[COMPLETED_STEP_IDS_STATE_KEY] = completed
        ctx.session.state[LAST_STEP_STATE_KEY] = entry
        ctx.session.state[CURRENT_STEP_STATE_KEY] = {}

    def _set_completed_steps(
        self, ctx: InvocationContext, completed_step_ids: list[str]
    ) -> None:
        ctx.session.state[COMPLETED_STEP_IDS_STATE_KEY] = list(completed_step_ids)

    def _mark_plan_complete(self, ctx: InvocationContext) -> None:
        plan_payload = ctx.session.state.get(PLAN_STATE_KEY) or {}
        if not plan_payload:
            return
        plan = orchestrated_models.Plan.model_validate(plan_payload)
        ctx.session.state[COMPLETED_STEP_IDS_STATE_KEY] = [
            step.id for step in plan.steps
        ]

    def _next_pending_step(
        self, ctx: InvocationContext
    ) -> Optional[orchestrated_models.PlanStep]:
        plan_payload = ctx.session.state.get(PLAN_STATE_KEY) or {}
        if not plan_payload:
            return None
        plan = orchestrated_models.Plan.model_validate(plan_payload)
        completed = set(ctx.session.state.get(COMPLETED_STEP_IDS_STATE_KEY) or [])
        for step in plan.steps:
            if step.id not in completed:
                return step
        return None

    def _fallback_answer(self, verification: orchestrated_models.Verification) -> str:
        if verification.answer.strip():
            return verification.answer.strip()
        if verification.writer_brief.strip():
            return verification.writer_brief.strip()
        if verification.missing_information:
            return "I could not fully verify the answer yet. Missing information: {items}.".format(
                items="; ".join(verification.missing_information),
            )
        return (
            "I could not complete a fully verified answer with the available evidence."
        )

    def _thinking_event(
        self,
        ctx: InvocationContext,
        *,
        step_id: str,
        label: str,
        detail: str,
        state: str,
    ) -> Event:
        return Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            custom_metadata={
                "platform_event": {
                    "type": "thinking_step",
                    "payload": {
                        "step_id": step_id,
                        "label": label,
                        "detail": detail,
                        "state": state,
                    },
                }
            },
        )

    def _hook_state(self, ctx: InvocationContext) -> contracts_hooks.HookState:
        state = ctx.session.state.get(HOOK_STATE_KEY)
        if isinstance(state, dict):
            return state
        refreshed = self.agent_hooks.create_turn_state(
            agent_id=self.name,
            user_id=str(getattr(ctx.session, "user_id", "") or ""),
            session_id=str(
                getattr(ctx.session, "id", getattr(ctx.session, "session_id", "")) or ""
            ),
            message=_current_user_text(ctx),
        )
        ctx.session.state[HOOK_STATE_KEY] = refreshed
        return refreshed

    def _final_answer_event(self, ctx: InvocationContext, answer: str) -> Event:
        final_answer = self.agent_hooks.finalize_response(
            text=answer,
            state=self._hook_state(ctx),
        )
        return Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            turn_complete=True,
            content=types.Content(role="model", parts=[types.Part(text=final_answer)]),
        )

    async def _stream_writer(self, ctx: InvocationContext):
        assembled_text = ""
        async with aclosing(self.writer_agent.run_async(ctx)) as agen:
            async for event in agen:
                hook_state = self._hook_state(ctx)
                for response in event.get_function_responses() or []:
                    self.agent_hooks.on_tool_response(
                        state=hook_state,
                        tool_name=response.name,
                        payload=response.response,
                    )
                ctx.session.state[HOOK_STATE_KEY] = hook_state

                if event.author != self.writer_agent.name:
                    continue

                text = _event_text(event)
                if getattr(event, "partial", False) and text:
                    assembled_text += text
                    yield Event(
                        author=self.name,
                        invocation_id=ctx.invocation_id,
                        partial=True,
                        content=types.Content(
                            role="model", parts=[types.Part(text=text)]
                        ),
                    )
                    continue

                if event.is_final_response() and (text or assembled_text):
                    final_text = "{buffer}{tail}".format(
                        buffer=assembled_text, tail=text
                    ).strip()
                    yield self._final_answer_event(ctx, final_text)
                    return

        verification_payload = ctx.session.state.get(VERIFICATION_STATE_KEY) or {}
        verification = (
            orchestrated_models.Verification.model_validate(verification_payload)
            if verification_payload
            else orchestrated_models.Verification(
                ready=False,
                rationale="Writer returned no final text.",
            )
        )
        fallback = (
            verification.answer.strip()
            or verification.writer_brief.strip()
            or self._fallback_answer(verification)
        )
        yield self._final_answer_event(ctx, fallback)


def build_orchestrated_controller(
    *,
    agent_name: str,
    description: str,
    system_prompt: str,
    model_name: str,
    tool_callables: Sequence[Callable[..., Any]],
    tool_definitions: Sequence[Any],
    execution_config: contracts_execution.ExecutionConfig,
    agent_hooks: contracts_hooks.AgentHooks,
    before_model_callback: Callable[[Any, Any], Any],
) -> OrchestratedController:
    planner_agent = LlmAgent(
        name="{name}_planner".format(name=agent_name),
        description="Creates a concrete execution plan.",
        model=model_name,
        instruction=lambda ctx: orchestrated_prompts.planner_instruction(
            agent_name=agent_name,
            system_prompt=system_prompt,
            tool_definitions=tool_definitions,
            ctx=ctx,
            hook_guidance=agent_hooks.build_prompt_guidance(
                phase="planner",
                state=_hook_state_from_context(ctx),
            ),
        ),
        include_contents="none",
        output_schema=orchestrated_models.Plan,
        output_key=PLANNER_OUTPUT_KEY,
        before_model_callback=before_model_callback,
    )
    executor_agent = LlmAgent(
        name="{name}_executor".format(name=agent_name),
        description="Executes the current step using available tools.",
        model=model_name,
        instruction=lambda ctx: orchestrated_prompts.executor_instruction(
            agent_name=agent_name,
            system_prompt=system_prompt,
            tool_definitions=tool_definitions,
            ctx=ctx,
            hook_guidance=agent_hooks.build_prompt_guidance(
                phase="executor",
                state=_hook_state_from_context(ctx),
            ),
        ),
        include_contents="none",
        tools=list(tool_callables),
        before_model_callback=before_model_callback,
    )
    replanner_agent = LlmAgent(
        name="{name}_replanner".format(name=agent_name),
        description="Decides whether to continue, replan, or finalize.",
        model=model_name,
        instruction=lambda ctx: orchestrated_prompts.replanner_instruction(
            agent_name=agent_name,
            system_prompt=system_prompt,
            ctx=ctx,
            hook_guidance=agent_hooks.build_prompt_guidance(
                phase="replanner",
                state=_hook_state_from_context(ctx),
            ),
        ),
        include_contents="none",
        output_schema=orchestrated_models.Decision,
        output_key=REPLANNER_OUTPUT_KEY,
        before_model_callback=before_model_callback,
    )
    verifier_agent = LlmAgent(
        name="{name}_verifier".format(name=agent_name),
        description="Checks whether the evidence is enough and prepares final-answer guidance.",
        model=model_name,
        instruction=lambda ctx: orchestrated_prompts.verifier_instruction(
            agent_name=agent_name,
            system_prompt=system_prompt,
            ctx=ctx,
            hook_guidance=agent_hooks.build_prompt_guidance(
                phase="verifier",
                state=_hook_state_from_context(ctx),
            ),
        ),
        include_contents="none",
        output_schema=orchestrated_models.Verification,
        output_key=VERIFIER_OUTPUT_KEY,
        before_model_callback=before_model_callback,
    )
    writer_agent = LlmAgent(
        name="{name}_writer".format(name=agent_name),
        description="Streams the final user-facing answer from the verified evidence.",
        model=model_name,
        instruction=lambda ctx: orchestrated_prompts.writer_instruction(
            agent_name=agent_name,
            system_prompt=system_prompt,
            ctx=ctx,
            hook_guidance=agent_hooks.build_prompt_guidance(
                phase="writer",
                state=_hook_state_from_context(ctx),
            ),
        ),
        include_contents="none",
        before_model_callback=before_model_callback,
    )
    return OrchestratedController(
        name=agent_name,
        description=description,
        planner_agent=planner_agent,
        executor_agent=executor_agent,
        replanner_agent=replanner_agent,
        verifier_agent=verifier_agent,
        writer_agent=writer_agent,
        execution_config=execution_config,
        agent_hooks=agent_hooks,
        sub_agents=[
            planner_agent,
            executor_agent,
            replanner_agent,
            verifier_agent,
            writer_agent,
        ],
    )


def _event_text(event: Event) -> str:
    if not event.content or not event.content.parts:
        return ""
    return "".join(
        part.text for part in event.content.parts if getattr(part, "text", None)
    )


def _hook_state_from_context(ctx: ReadonlyContext) -> contracts_hooks.HookState:
    state = getattr(ctx, "state", None) or {}
    hook_state = state.get(HOOK_STATE_KEY)
    if isinstance(hook_state, dict):
        return hook_state
    return {}


def _current_user_text(ctx: InvocationContext) -> str:
    user_content = getattr(ctx, "user_content", None)
    if not user_content or not getattr(user_content, "parts", None):
        return ""
    return "".join(
        part.text for part in user_content.parts if getattr(part, "text", None)
    )
