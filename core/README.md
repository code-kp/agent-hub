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
- `hooks.py`
  - Defines `AgentHooks`
  - This is the runtime extension point for agent-specific prompt guidance, per-turn state, and final response shaping
- `memory.py`
  - Defines `MemoryConfig`
  - This controls whether an agent uses compact rolling memory
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
  - Parses markdown skill files into `SkillDefinition`
  - Uses folder-based `behavior` / `knowledge` classification
- `store.py`
  - Maintains the in-memory skill catalog and chunk index
- `resolver.py`
  - Resolves which skills should be included for a request
  - Applies always-on behavior skill loading, knowledge retrieval, lexical scoring, and chunk selection
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

### `core/execution/`

Per-agent execution package.

- `direct/`
  - Direct model-led tool-calling runtime
- `orchestrated/`
  - Explicit `plan -> execute -> replan -> verify` runtime
- `shared/`
  - ADK helpers, guarded tool wrapping, and shared execution types
- `factory.py`
  - Picks the right execution runtime for each agent definition

### `core/memory/`

Conversation-memory compaction.

- `context.py`
  - Defines normalized memory messages and the prompt-ready memory snapshot
- `store.py`
  - Maintains rolling per-session memory state
- `summarizer.py`
  - Uses ADK to compress older turns into a compact summary
- `manager.py`
  - Handles seeding, summarization, and recent-turn retention

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
3. `core/execution/direct/runtime.py` or `core/execution/orchestrated/runtime.py` receives a user message
4. `core/skills/resolver.py` picks relevant skill summaries and excerpts
5. `core/execution/direct/prompts.py` or `core/execution/orchestrated/prompts.py` injects that context and gives the model the available tool catalog
6. `core/memory/manager.py` injects compact memory when the agent enables it
7. the ADK agent decides whether tools are needed and may chain them iteratively
8. `core/guardrails.py` enforces framework limits during tool execution
9. `core/stream/progress.py` emits live events to the UI

## Where Logic Should Live

Use this split consistently.

### Put it in the agent if it is:

- persona
- response style
- answer format
- domain behavior
- synthesis strategy after information is available
- agent-specific prompt augmentation or final response post-processing

Examples:
- "Answer in 1-4 sentences"
- "Prefer concise support responses"
- "Use internal guidance before web research when possible"
- "Rewrite bare citation numbers into clickable links for web agents"

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

- behavior guidance that should always shape the agent
- reusable domain knowledge that should be retrieved when relevant
- a workflow or operating procedure that belongs in `knowledge`
- persona instructions or response boundaries shared across agents

Examples:
- `behavior`: support response boundaries, agent persona
- `knowledge`: refund policy, incident triage workflow

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
- use `AgentModule` for simple direct tool-calling agents
- use `OrchestratedAgentModule` when you want the framework to run an explicit `plan -> execute -> replan -> verify` loop
- keep the system prompt focused on behavior, not retrieval plumbing
- list only explicit tools by name
- use `behavior` for always-on behavior shaping
- use `knowledge` for retrievable reference material
- use `memory` when you want compact follow-up context without replaying the full transcript
- let the model plan tool usage; use `ExecutionConfig` only for tool-loop limits and guardrails
- use `hooks` when one agent family needs custom prompt guidance or final response shaping that should not live in `core`

Example:

```python
from core.contracts.agent import AgentModule, register_agent_class
from core.contracts.execution import ExecutionConfig
from core.contracts.memory import MemoryConfig
from core.contracts.models import lite_llm_model


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
    behavior = (
        "support.persona",
        "support.policy",
    )
    knowledge = (
        "support.triage",
        "general.product",
    )
    model = lite_llm_model("openai/gpt-4o-mini")
    execution = ExecutionConfig(
        max_tool_calls=6,
        max_calls_per_tool=2,
    )
    memory = MemoryConfig(
        enabled=True,
        preserve_recent_turns=4,
        summarize_after_turns=6,
    )
```

Model selection:
- native ADK/Gemini: `model = "gemini-2.0-flash"`
- LiteLLM through ADK: `model = lite_llm_model("openai/gpt-4o-mini")`
- LiteLLM references must be explicit `provider/model` values such as `openai/gpt-4o-mini` or `gemini/gemini-2.0-flash`
- env override:
  - `MODEL_NAME=gemini-2.0-flash`
  - `MODEL_NAME=openai/gpt-4o-mini` with `MODEL_BACKEND=litellm`
  - or `MODEL_NAME=litellm:openai/gpt-4o-mini`

Hook example:

```python
from core.contracts.agent import AgentModule, register_agent_class
from workspace.agents.web.hooks import WebCitationHooks


@register_agent_class
class WebAnswer(AgentModule):
    name = "Web Answer"
    description = "Answers using public web sources."
    system_prompt = "Answer clearly and cite web evidence inline."
    tools = ("search_web", "fetch_web_page")
    hooks = WebCitationHooks()
```

Do not:
- hardcode file paths into agent definitions
- put large domain knowledge directly in the system prompt
- use one giant behavior skill for everything

Implicit framework tools:
- `search_skills` is included through the default core toolset
- agent authors should not keep re-listing framework tools in every agent definition
- tool planning is model-driven; the framework only enforces budgets and repetition limits

Agent interfaces:
- `AgentModule`: direct ADK agent runtime; the model decides tool calls directly
- `OrchestratedAgentModule`: ADK custom-controller runtime; the framework runs planner, executor, replanner, and verifier sub-agents for you
- `MemoryConfig`: compact rolling memory; the framework keeps a summary plus a few recent turns instead of replaying the full transcript

Orchestrated example:

```python
from core.contracts.agent import OrchestratedAgentModule, register_orchestrated_agent_class
from core.contracts.execution import ExecutionConfig


@register_orchestrated_agent_class
class WebResearch(OrchestratedAgentModule):
    name = "Web Research"
    description = "Plans, researches, verifies, and answers using public web sources."
    system_prompt = "Answer thoroughly, verify important claims, and cite external evidence inline."
    tools = (
        "get_current_utc_time",
        "search_web",
        "fetch_web_page",
    )
    execution = ExecutionConfig(
        max_tool_calls=8,
        max_replans=3,
        max_verification_rounds=2,
    )
```

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
- put it under either `workspace/skills/behavior/...` or `workspace/skills/knowledge/...`
- use a heading and normal markdown content
- let the framework infer the title from the first heading or file name
- let the framework infer the summary from the first paragraph
- keep `behavior` skills short and stable
- keep `knowledge` skills focused enough for precise retrieval

Example:

```md
# Support Response Policy

- Lead with mitigation when production is affected.
- Distinguish facts from assumptions.
- Do not invent incident status.
```

Folder meaning:
- `behavior`
  - always-on behavior shaping
  - examples: persona, response boundaries, tone guidance
- `knowledge`
  - retrievable reference material
  - examples: product docs, workflows, FAQs, policies, release notes

Inside `behavior`, the common sub-patterns are:
- `persona`
  - how the agent should sound and behave
  - examples: concise replies, operational tone, low speculation
- `policy`
  - rules and boundaries the agent should follow
  - examples: do not invent status, separate facts from assumptions, require verification before commitments

Public ids come from the path after `behavior/` or `knowledge/`:
- `workspace/skills/behavior/support/policy.md` -> `support.policy`
- `workspace/skills/knowledge/support/triage.md` -> `support.triage`

Agent definitions should list exact ids:
- `behavior = ("support.persona", "support.policy")`
- `knowledge = ("support.triage", "general.product")`

Do not:
- combine behavior guidance and large reference material into one large markdown file
- put unrelated support knowledge into one huge document
- require contributors to author retrieval metadata before they can add a useful skill

## Design Principle

Keep the architecture layered:

- `contracts`: what contributors write
- `skills`: what the platform retrieves
- `stream`: what the UI sees
- `guardrails`: what the platform guarantees deterministically
- `execution`: what executes the full loop

If a change makes those boundaries blur, it will make the platform harder to maintain.
