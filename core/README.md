# Core Architecture

`core/` is the platform runtime. It should stay implementation-focused and stable.

Use `workspace/` to add agents, tools, and skills. Use `core/` to change how the platform discovers, resolves, streams, and executes them.

## Package Map

### `core/contracts/`

Author-facing definitions.

- `agent.py`
  - Defines `Agent`, `AgentModule`, `define_agent()`, and `register_agent_class()`
  - This is the main API for defining agents
- `execution.py`
  - Defines `ExecutionConfig`
  - This is the runtime contract for execution limits and guardrails
- `tools.py`
  - Defines `ToolDefinition`, `ToolModule`, `register_tool_class()`, and `ProgressUpdater`
  - This is the main API for defining tools
- `skills.py`
  - Defines `SkillDefinition` plus scope/id normalization helpers
  - This is the normalized metadata shape for markdown skills after discovery

Rule:
- If a contributor is writing an agent or tool, this is the package they should import from

### `core/builtin_tools/`

Framework-provided shared tools.

- `skills.py`
  - Registers built-in skill-library tools such as `search_skills`
  - These tools are available to agents without each author defining them in `workspace/tools/`

Rule:
- Put truly framework-wide tools here
- Do not duplicate them in `workspace/tools/`

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

### `core/guardrails.py`

Deterministic runtime limits.

- Enforces framework-owned decisions during the tool loop
- Example:
  - total tool-call budget per turn
  - per-tool call limits
  - duplicate tool-call blocking

Rule:
- Framework guarantees belong here
- This is where to put deterministic limits and safety constraints
- Do not put tool-specific planning logic here

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

### `core/runtime/`

Per-agent execution package.

- `engine.py`
  - Owns per-turn orchestration and runtime lifecycle
- `prompts.py`
  - Builds agent instructions, runtime context injection, and tool reasoning text
- `adk.py`
  - Wraps ADK agent creation and threaded event streaming helpers
- `tooling.py`
  - Applies execution guardrails to tool callables
- `types.py`
  - Defines `AgentRecord`

Responsibilities:
- build the ADK agent
- resolve skills per request
- inject skill context into the model request
- let the model decide whether tools are needed and in what sequence
- enforce framework guardrails during tool execution
- bind the active skill store so framework tools like `search_skills` can access the current workspace skill catalog
- stream thinking/debug/assistant events back to the caller

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
3. `core/runtime/engine.py` receives a user message
4. `core/skills/resolver.py` picks relevant skill summaries and excerpts
5. `core/runtime/prompts.py` injects that context and gives the model the available tool catalog
6. the ADK agent decides whether tools are needed and may chain them iteratively
7. `core/guardrails.py` enforces framework limits during tool execution
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

### Put it in framework guardrails if it is:

- a platform guarantee about safety or limits
- deterministic execution control
- something that should constrain tool execution, not decide user intent

Examples:
- maximum tool calls per turn
- maximum repeated calls to the same tool
- blocking exact duplicate tool calls

## Best Practices

### Best way to define an agent

Recommended:
- use `AgentModule`
- keep the system prompt focused on behavior, not retrieval plumbing
- list only explicit tools by name
- use `skill_scopes` to declare what knowledge the agent is allowed to use
- use `always_on_skills` only for small, stable skills
- let the model plan tool usage; use `ExecutionConfig` only for limits and guardrails

Example:

```python
from core.contracts.agent import AgentModule, register_agent_class
from core.contracts.execution import ExecutionConfig


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
    )
    skill_scopes = (
        "support.*",
        "general.*",
    )
    always_on_skills = (
        "support.persona",
        "support.policy",
    )
    execution = ExecutionConfig(
        max_tool_calls=6,
        max_calls_per_tool=2,
    )
```

Do not:
- hardcode file paths into agent definitions
- put large domain knowledge directly in the system prompt
- use one giant `always_on` skill for everything

Implicit framework tools:
- `search_skills` is included through the default core toolset
- agent authors should not keep re-listing framework tools in every agent definition
- tool planning is model-driven by default; the framework only enforces budgets and repetition limits

### Best way to define a tool

Recommended:
- use `ToolModule`
- write a description that explains when to use it
- fill in `category`, `use_when`, `avoid_when`, and `returns`
- emit user-facing narration with `self.progress.think(...)`
- emit raw developer detail with `self.progress.debug(...)`
- keep the handler focused on execution, not global orchestration

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
