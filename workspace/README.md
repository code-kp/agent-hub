# Workspace

Everything contributors need lives here:

- `agents/` for agent modules
- `tools/` for shared tool modules
- `skills/` for markdown skills

Rules:

- Agent ids come from the directory hierarchy under `agents/`
- Tool modules are loaded before agent modules, so agents can reference tools by name
- Skill ids come from the directory hierarchy under `skills/`
- Skill files should live under either `skills/behavior/` or `skills/knowledge/`
- Agents should use `behavior` and `knowledge`
- `skill_scopes`, `always_on_skills`, and `skills_dir` still load for compatibility, but are no longer the recommended authoring model

Use [../core/README.md](../core/README.md) for platform internals.
Use this file for contributor-facing authoring rules.

## Best Way To Define An Agent

Recommended:
- use one class per agent module
- inherit from `AgentModule` for simple direct tool-calling agents
- inherit from `OrchestratedAgentModule` when you want the framework to drive `plan -> execute -> replan -> verify`
- register with `@register_agent_class`
- keep the prompt focused on behavior and synthesis
- reference only explicit tools by name
- use `behavior` for always-on behavior shaping
- use `knowledge` for retrievable reference material
- use `memory` when the agent should carry compact follow-up context across turns
- let the model decide whether tools are needed; use `execution` only for tool-loop limits and guardrails
- use `hooks` only for agent-specific prompt additions or final response shaping that should not move into `core`

Example:

```python
from core.contracts.agent import AgentModule, register_agent_class
from core.contracts.execution import ExecutionConfig
from core.contracts.memory import MemoryConfig


@register_agent_class
class MyAgent(AgentModule):
    name = "My Agent"
    description = "What it does"
    system_prompt = "How it should behave"
    tools = ("get_current_utc_time",)
    behavior = ("general.persona",)
    knowledge = ("general.product",)
    execution = ExecutionConfig(max_tool_calls=6)
    memory = MemoryConfig(enabled=True, preserve_recent_turns=4, summarize_after_turns=6)
```

If you want the agent to stay stateless, set:

```python
from core.contracts.memory import DISABLED_MEMORY_CONFIG

memory = DISABLED_MEMORY_CONFIG
```

Hook example:

```python
from core.contracts.agent import AgentModule, register_agent_class
from core.contracts.hooks import AgentHooks


class MyHooks(AgentHooks):
    def finalize_response(self, *, text, state):
        return text.strip()


@register_agent_class
class MyAgent(AgentModule):
    name = "My Agent"
    description = "What it does"
    system_prompt = "How it should behave"
    tools = ("search_web",)
    hooks = MyHooks()
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

Orchestrated example:

```python
from core.contracts.agent import OrchestratedAgentModule, register_orchestrated_agent_class
from core.contracts.execution import ExecutionConfig


@register_orchestrated_agent_class
class ResearchAgent(OrchestratedAgentModule):
    name = "Research Agent"
    description = "Plans and verifies before answering."
    system_prompt = "Answer with verification and cite external evidence inline."
    tools = ("get_current_utc_time", "search_web", "fetch_web_page")
    execution = ExecutionConfig(max_tool_calls=8, max_replans=3, max_verification_rounds=2)
```

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

Put skills in one of these folders:

- `workspace/skills/behavior/...`
- `workspace/skills/knowledge/...`

That is the whole public model:

- `behavior`
  - always-on behavior shaping
  - examples: persona, response boundaries, tone guidance
- `knowledge`
  - retrievable reference material
  - examples: product facts, workflows, FAQs, policies, docs

Inside `behavior`, the two common patterns are:

- `persona`
  - how the agent should sound and behave
  - examples: be concise, be calm, be operational
- `policy`
  - rules and boundaries the agent should follow
  - examples: do not invent status, separate facts from assumptions, require verification before commitments

Recommended:
- one concern per skill
- use a heading and normal markdown content
- let the framework infer title from the first heading or the file name
- let the framework infer summary from the first paragraph
- keep `behavior` files short and stable
- keep `knowledge` files focused so retrieval can stay precise

Example:

```md
# Refund Policy

Refunds are available for annual plans within 30 days of the original purchase.

- Monthly plans are not refundable after the billing cycle starts.
- Annual upgrades can be prorated if the customer is moving to enterprise.
```

Public ids come from the path after `behavior/` or `knowledge/`:

- `workspace/skills/behavior/support/persona.md` -> `support.persona`
- `workspace/skills/knowledge/support/refunds.md` -> `support.refunds`

Agents should list exact ids:

- `behavior = ("support.persona", "support.policy")`
- `knowledge = ("support.refunds", "general.product")`

Avoid:
- mixing behavior guidance and large reference docs into one file
- putting all support knowledge into one giant markdown file
- requiring authors to think about retrieval metadata before they can write a useful skill

Compatibility note:
- frontmatter still loads if it already exists
- old `skill_scopes` and `always_on_skills` still work during migration
- `behavior_skills` and `knowledge_skills` still work during migration
- new docs and examples should use `behavior` and `knowledge`

## Namespace Rules

- `workspace/agents/general.py` -> agent id `general`
- `workspace/agents/support/triage.py` -> agent id `support.triage`
- `workspace/skills/behavior/support/policy.md` -> skill id `support.policy`
- `workspace/skills/knowledge/general/product.md` -> skill id `general.product`

## Design Rule

Keep contributor code simple:
- agents decide behavior and answer style
- tools execute actions
- skills hold reusable knowledge/instructions

Do not push platform orchestration into workspace code unless there is a clear need.
Do keep agent-specific formatting and post-processing in hooks instead of adding those rules to `core`.
