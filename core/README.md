# Core Architecture

`core/` is the platform runtime. It should stay implementation-focused and stable.

Use `workspace/` to add agents, tools, and skills. Use `core/` to change how the platform discovers, resolves, streams, and executes them.

## Package Map

### `core/contracts/`

Author-facing definitions.

- `agent.py`
  - Defines `Agent`, `AgentModule`, `define_agent()`, and `register_agent_class()`
  - This is the main API for defining agents
- `tools.py`
  - Defines `ToolDefinition`, `@tool(...)`, `create_tool()`, and `ProgressUpdater`
  - This is the main API for defining tools
- `skills.py`
  - Defines `SkillDefinition` plus scope/id normalization helpers
  - This is the normalized metadata shape for markdown skills after discovery

Rule:
- If a contributor is writing an agent or tool, this is the package they should import from

### `core/skills/`

Skill ingestion and retrieval.

- `parser.py`
  - Parses markdown skill files and frontmatter into `SkillDefinition`
- `store.py`
  - Maintains the in-memory skill catalog and chunk index
- `resolver.py`
  - Resolves which skills should be included for a request
  - Applies scopes, always-on rules, lexical scoring, and chunk selection
- `uploads.py`
  - Writes uploaded markdown files into the workspace skill tree

Rule:
- This package owns skill loading and selection logic
- Agents should not implement their own skill resolution logic

### `core/stream/`

Live event streaming and narration.

- `messages.py`
  - Converts runtime events into readable text
- `progress.py`
  - Provides the async event stream and helpers for `thinking` and `debug` events

Rule:
- If something needs to appear in the UI live, it should flow through this package

### `core/policies/`

Deterministic orchestration logic.

- `tool_policy.py`
  - Decides whether a request requires preflight tools before the model runs
  - Example: current/public question -> `get_current_utc_time -> search_web`
- `search_strategy.py`
  - Builds search plans and query variants
  - Owns date anchoring and query expansion

Rule:
- Hard guarantees belong here
- This is where to place deterministic planning logic that should not rely on model judgment

## Top-Level Modules

### `core/discovery.py`

Runtime discovery for:
- `workspace/tools`
- `workspace/agents`
- `workspace/skills`

Responsibilities:
- load tool modules before agents
- derive agent ids from the `workspace/agents` module path
- derive skill ids from the `workspace/skills` path
- register discovered skills and prepare discovered agent records

### `core/platform.py`

Main platform facade.

Responsibilities:
- refresh discovery
- rebuild runtimes when definitions change
- expose agent catalog/tree
- stream chat
- accept uploaded markdown and refresh skills

Use this when:
- you want one top-level object that represents the platform runtime

### `core/runtime.py`

Per-agent execution engine.

Responsibilities:
- build the ADK agent
- resolve skills per request
- plan required preflight tools
- run required tools before model execution
- inject skill context and preflight results into the model request
- stream thinking/debug/assistant events back to the caller

This is the module that turns:
- agent definition
- tool definitions
- skill resolution
- streaming

into one working chat loop.

### `core/registry.py`

Global typed registry.

Responsibilities:
- register and fetch things by `(type, name)`
- keep the runtime loosely coupled from discovery order

Examples:
- `Register.get(Agent, "Web Answer")`
- `Register.get(ToolDefinition, "search_web")`
- `Register.get(SkillDefinition, "support.triage")`

## Execution Flow

1. `core/discovery.py` scans `workspace/`
2. `core/platform.py` refreshes the catalog and runtimes
3. `core/runtime.py` receives a user message
4. `core/skills/resolver.py` picks relevant skill summaries and excerpts
5. `core/policies/tool_policy.py` decides whether any required tools must run first
6. preflight tool outputs are injected into the model context
7. the ADK agent may still call additional tools
8. `core/stream/progress.py` emits live events to the UI

## Where Logic Should Live

Use this split consistently.

### Put it in the agent if it is:

- persona
- response style
- answer format
- domain behavior
- synthesis strategy after information is available

Examples:
- "Answer in 1-4 sentences"
- "Prefer concise support responses"
- "Use internal guidance before web research when possible"

### Put it in a tool if it is:

- direct interaction with an external system
- data fetching
- computation
- transformation
- side effects

Examples:
- search the web
- fetch a page
- read current time
- query a database

### Put it in skills if it is:

- reusable domain knowledge
- policy
- workflow
- persona instructions shared across agents

Examples:
- refund policy
- incident triage workflow
- support response boundaries
- agent persona

### Put it in policies if it is:

- a platform guarantee
- deterministic orchestration
- a rule that should not depend on model choice

Examples:
- current/public request must preflight web search
- exact time request must preflight the time tool
- search query expansion should use current date when the request is time-sensitive

## Best Practices

### Best way to define an agent

Recommended:
- use `AgentModule`
- keep the system prompt focused on behavior, not retrieval plumbing
- list tools by name
- use `skill_scopes` to declare what knowledge the agent is allowed to use
- use `always_on_skills` only for small, stable skills

Example:

```python
from core.contracts.agent import AgentModule, register_agent_class


@register_agent_class
class SupportTriage(AgentModule):
    name = "Support Triage"
    description = "Handles operational support questions."
    system_prompt = (
        "Answer clearly and concisely. Use internal guidance first when it is enough. "
        "When current public information is needed, rely on the available web tools."
    )
    tools = (
        "get_current_utc_time",
        "search_web",
        "fetch_web_page",
        "search_skills",
    )
    skill_scopes = (
        "support.*",
        "general.*",
    )
    always_on_skills = (
        "support.persona",
        "support.policy",
    )
```

Do not:
- hardcode file paths into agent definitions
- put large domain knowledge directly in the system prompt
- use one giant `always_on` skill for everything

### Best way to define a tool

Recommended:
- use `@tool(...)`
- write a description that explains when to use it
- fill in `category`, `use_when`, `avoid_when`, and `returns`
- emit user-facing narration with `progress.think(...)`
- emit raw developer detail with `progress.debug(...)`
- keep the handler focused on execution, not global orchestration

Example:

```python
from core.contracts.tools import current_progress, tool


@tool(
    description="Return the current UTC time.",
    category="time",
    use_when=(
        "The request asks for the current time or date.",
        "A time-sensitive answer should be anchored before searching fresh sources.",
    ),
    returns="A UTC timestamp in ISO 8601 format.",
    requires_current_data=True,
    follow_up_tools=("search_web",),
)
def get_current_utc_time() -> dict:
    progress = current_progress()
    progress.think(
        "Checking the current time",
        detail="Confirming the current UTC time before answering.",
        step_id="get_current_utc_time",
    )
    ...
```

Do not:
- make the description generic
- dump raw dicts to the user-facing thinking trace
- embed platform policy inside each tool

### Best way to define a skill

Recommended:
- keep one skill focused on one concern
- use frontmatter consistently
- use `persona` for behavior-shaping guidance
- use `policy` for constraints and rules
- use `workflow` for step-by-step operating procedures
- use `knowledge` for facts, guides, docs, references

Example:

```md
---
title: Support Response Policy
type: policy
summary: Boundaries and priorities for support conversations.
tags: [support, policy]
triggers: [incident, outage, production, urgent]
mode: always_on
priority: 90
---

# Support Response Policy

- Lead with mitigation when production is affected.
- Distinguish facts from assumptions.
- Do not invent incident status.
```

Use `mode` like this:
- `always_on`
  - small, stable instructions that should usually be present
- `auto`
  - normal retrievable skills selected per request
- `manual`
  - only use when explicitly selected by a tool or future UI flow

Do not:
- combine persona, policy, workflow, and product docs into one large markdown file
- use long summaries
- rely on folder names alone without frontmatter quality

## Design Principle

Keep the architecture layered:

- `contracts`: what contributors write
- `skills`: what the platform retrieves
- `stream`: what the UI sees
- `policies`: what the platform guarantees
- `runtime`: what executes the full loop

If a change makes those boundaries blur, it will make the platform harder to maintain.
