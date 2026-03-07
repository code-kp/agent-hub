# Workspace

Everything contributors need lives here:

- `agents/` for agent modules
- `tools/` for shared tool modules
- `skills/` for markdown skills

Rules:

- Agent ids come from the directory hierarchy under `agents/`
- Tool modules are loaded before agent modules, so agents can reference tools by name
- Skill ids come from the directory hierarchy under `skills/`
- Skill files should have frontmatter metadata (`title`, `type`, `summary`, `tags`, `triggers`, `mode`, `priority`)
- Agents select skills with `skill_scopes` and `always_on_skills`, not a single `skills_dir`

Use [../core/README.md](../core/README.md) for platform internals.
Use this file for contributor-facing authoring rules.

## Best Way To Define An Agent

Recommended:
- use one class per agent module
- inherit from `AgentModule`
- register with `@register_agent_class`
- keep the prompt focused on behavior and synthesis
- reference only explicit tools by name
- use `skill_scopes` to define allowed knowledge
- use `always_on_skills` only for small persona/policy skills
- let the model decide whether tools are needed; use `execution` only for tool-loop limits

Example:

```python
from core.contracts.agent import AgentModule, register_agent_class
from core.contracts.execution import ExecutionConfig


@register_agent_class
class MyAgent(AgentModule):
    name = "My Agent"
    description = "What it does"
    system_prompt = "How it should behave"
    tools = ("get_current_utc_time",)
    skill_scopes = ("general",)
    always_on_skills = ("general.persona",)
    execution = ExecutionConfig(max_tool_calls=6)
```

Better prompt shape:
- what kind of answers it should produce
- what tradeoffs it should make
- when to prefer internal guidance vs web research

Avoid:
- hardcoding file paths
- putting large policy/knowledge blocks into the prompt
- relying on one giant always-on skill for all behavior

Implicit framework tools:
- `search_skills` is automatically available through the default core toolset
- do not add it explicitly unless you are intentionally overriding the default model
- reserve `tools = (...)` for explicit capabilities like web search, time, APIs, or integrations

## Best Way To Define A Tool

Put tools in `workspace/tools/*.py`.

Recommended:
- use `ToolModule`
- give the tool a concrete description
- set metadata like `category`, `use_when`, `avoid_when`, and `returns`
- use `self.progress` and emit:
  - `progress.think(...)` for user-facing narration
  - `progress.debug(...)` for raw execution detail

Example:

```python
from core.contracts.tools import ToolModule, register_tool_class


@register_tool_class
class GetCurrentUtcTimeTool(ToolModule):
    name = "get_current_utc_time"
    description = "Return the current UTC time."
    category = "time"
    use_when = (
        "The request asks for the current time or date.",
        "A time-sensitive answer should be anchored before searching fresh sources.",
    )
    returns = "A UTC timestamp in ISO 8601 format."
    requires_current_data = True
    follow_up_tools = ("search_web",)

    def run(self) -> dict:
        self.progress.think(
            "Checking the current time",
            detail="Confirming the current UTC time before answering.",
            step_id="get_current_utc_time",
        )
        ...
```

Avoid:
- generic descriptions like "search things"
- exposing raw dicts as user-facing progress text
- placing platform-wide execution limits or safety guarantees inside the tool handler

## Best Way To Define A Skill

Put skills in `workspace/skills/**/*.md`.

Recommended:
- one concern per skill
- high-quality frontmatter
- short summary
- meaningful triggers and tags

Use the skill types like this:
- `persona`
  - short guidance that shapes how the agent behaves
- `policy`
  - rules, boundaries, constraints
- `workflow`
  - step-by-step operating procedures
- `knowledge`
  - factual docs, references, FAQs, release notes

Example:

```md
---
title: Refund Policy
type: policy
summary: Rules for handling refund questions.
tags: [refund, billing, policy]
triggers: [refund, cancel, annual plan]
mode: auto
priority: 80
---
```

Use `mode` like this:
- `always_on`
  - small, stable instructions that should usually be present
- `auto`
  - normal retrievable skills selected per request
- `manual`
  - reserved for explicit future selection paths

Avoid:
- mixing persona, policy, workflow, and docs into one file
- large summaries
- weak frontmatter that makes retrieval harder

## Namespace Rules

- `workspace/agents/general.py` -> agent id `general`
- `workspace/agents/support/triage.py` -> agent id `support.triage`
- `workspace/skills/general/product.md` -> skill id `general.product`
- `workspace/skills/support/policy.md` -> skill id `support.policy`

## Design Rule

Keep contributor code simple:
- agents decide behavior and answer style
- tools execute actions
- skills hold reusable knowledge/instructions

Do not push platform orchestration into workspace code unless there is a clear need.
