from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    success_criteria: str = Field(min_length=1)


class Plan(BaseModel):
    goal: str = Field(min_length=1)
    steps: list[PlanStep] = Field(default_factory=list)
    done_when: str = Field(min_length=1)


class Decision(BaseModel):
    action: Literal["continue", "replan", "finalize"]
    rationale: str = Field(min_length=1)
    updated_plan: Optional[Plan] = None


class Verification(BaseModel):
    ready: bool
    rationale: str = Field(min_length=1)
    answer: str = ""
    missing_information: list[str] = Field(default_factory=list)


def serialize_plan(plan: Plan | dict[str, Any] | None) -> dict[str, Any]:
    if plan is None:
        return {}
    if isinstance(plan, Plan):
        return plan.model_dump(exclude_none=True)
    return dict(plan)
