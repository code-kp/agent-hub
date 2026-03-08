# Agent Platform

Framework-style platform for creating and running custom agents with:

- strict separation of `core/` platform runtime and `workspace/` creator content
- one shared workspace for agents, tools, and skills
- class-based agent authoring API
- folder-based skill discovery with explicit behavior/knowledge assignment
- global typed registry (`Register.get(Type, name)`)
- runtime discovery of tools and agents on every API interaction
- streaming chat/tool/progress events to the UI

## Documentation

- [Core architecture](./core/README.md)
  - what each core module does
  - where discovery, runtime, execution guardrails, skill resolution, and streaming logic belong
- [Workspace authoring](./workspace/README.md)
  - how to define agents, tools, and skills in the shared workspace

## Structure

```text
core/
  contracts/
  builtin_tools/
  execution/
  skills/
  stream/
  guardrails.py
  discovery.py
  platform.py
  registry.py
workspace/
  agents/               # agent modules; directories become namespaces
  tools/                # shared tool modules; loaded before agents
  skills/               # shared markdown skills
api.py
server.py
frontend/
```

## Run

1. Set `GOOGLE_API_KEY` in `.env`
2. Install Python dependencies:

```bash
uv sync --all-groups --all-extras
```

3. Install frontend dependencies:

```bash
uv run poe frontend-install
```

4. Start backend + frontend:

```bash
uv run poe dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000)

## Poe Tasks

- `uv run poe backend`
- `uv run poe frontend`
- `uv run poe dev`
- `uv run poe stop`

## Authoring Agents

Create agent modules under:

- `workspace/agents/...`

Directories under `workspace/agents/` are namespaces. For example:

- `workspace/agents/general.py` -> agent id `general`
- `workspace/agents/support/triage.py` -> agent id `support.triage`

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
    tools = ("get_current_utc_time",)  # explicit tools only
    behavior = ("general.persona",)
    knowledge = ("general.product", "support.triage")
    execution = ExecutionConfig(max_tool_calls=6)
    memory = MemoryConfig(enabled=True, preserve_recent_turns=4, summarize_after_turns=6)
```

Best practice:
- keep `system_prompt` focused on behavior and output style
- keep domain knowledge in skills, not in the prompt
- use `behavior` for always-on behavior shaping
- use `knowledge` for retrievable reference material
- use `memory` when you want compact follow-up context with lower token growth
- rely on implicit framework tools like `search_skills` instead of listing them on every agent
- let the model decide whether tools are needed; use `execution` only for guardrails like tool-call budgets
- use `hooks` for agent-specific prompt additions or final response shaping instead of pushing those behaviors into `core`

If you want the framework to drive an explicit `plan -> execute -> replan -> verify` loop, use `OrchestratedAgentModule` instead:

```python
from core.contracts.agent import OrchestratedAgentModule, register_orchestrated_agent_class
from core.contracts.execution import ExecutionConfig


@register_orchestrated_agent_class
class ResearchAgent(OrchestratedAgentModule):
    name = "Research Agent"
    description = "Plans, executes, replans, and verifies before answering."
    system_prompt = "Answer thoroughly and verify important claims."
    tools = ("get_current_utc_time", "search_web", "fetch_web_page")
    execution = ExecutionConfig(max_tool_calls=8, max_replans=3, max_verification_rounds=2)
```

## Authoring Tools

Put tools under `workspace/tools/...` and define them as `ToolModule` classes.
All tools are loaded before agents, so any agent can reference any tool by name.

Example:

```python
from core.contracts.tools import ToolModule, register_tool_class


@register_tool_class
class GetCurrentUtcTimeTool(ToolModule):
    name = "get_current_utc_time"
    description = "Return UTC time."
    category = "time"
    use_when = ("The request asks for current time or date.",)
    returns = "A UTC timestamp in ISO 8601 format."

    def run(self) -> dict:
        self.progress.think(
            "Checking the current time",
            detail="Confirming the current UTC time.",
            step_id="get_current_utc_time",
        )
        ...
```

Best practice:
- fill in tool metadata well enough that the runtime and model can make good decisions
- emit `progress.think(...)` for user-facing narration
- emit `progress.debug(...)` for developer detail
- keep tool-specific planning with the tool itself; keep only hard execution limits in the framework

Framework-provided common tools:
- `search_skills` is included automatically for agents by the core toolset
- agent authors should only list explicit tools that expand the agent's capabilities, such as web search, time, APIs, or side-effecting integrations

## Authoring Skills

Put markdown skills under one of these folders:

Examples:

- `workspace/skills/behavior/general/persona.md`
- `workspace/skills/knowledge/support/triage.md`

Skill ids come from the directory hierarchy under `workspace/skills/`:

- `workspace/skills/behavior/general/persona.md` -> `general.persona`
- `workspace/skills/knowledge/support/triage.md` -> `support.triage`

There are only two user-facing skill classes:

```md
# behavior/support/persona.md

# Support Persona

Keep troubleshooting replies concrete and operational.
```

- `workspace/skills/behavior/...`
  - always-on behavior shaping
- `workspace/skills/knowledge/...`
  - retrievable knowledge and reference content

Within `behavior`, two common patterns are:

- `persona`
  - how the agent should sound and behave
  - examples: be concise, be operational, avoid speculation
- `policy`
  - rules and boundaries the agent should follow
  - examples: do not invent status, distinguish facts from assumptions, require verification before making commitments

Best practice:
- use a heading and normal markdown content
- let the framework infer title and summary
- keep one skill focused on one concern instead of mixing everything into one file
- use `behavior` only for guidance that should always shape the agent
- use `knowledge` for docs, workflows, references, policies, and FAQs

Agents now declare exact skill ids. The runtime:

- always loads `behavior`
- chooses from `knowledge` per request using lexical matching and chunk selection
- injects summaries first and only adds detailed excerpts for the top matches

The shared skill tools (`search_skills`, `list_skill_files`, `read_skill_file`) are framework-provided tools in `core/` rather than workspace tools. `search_skills` is available to agents through the default core toolset.

### Uploading Markdown As Skills

Use the backend upload endpoint to turn any markdown file into a skill:

```bash
curl -X POST http://127.0.0.1:8000/api/skills/upload \
  -F "file=@/path/to/refund-faq.md" \
  -F "user_id=browser-user" \
  -F "namespace=billing"
```

Uploaded files are stored under `workspace/skills/uploads/...` and are treated as knowledge skills.

That is the recommended default:

- use uploaded knowledge for docs, notes, guides, FAQs, release notes, and product references
- keep authored `behavior` skills for short, stable instructions that should shape how an agent behaves

`uploads.<user-id>.*` skills are treated as user-scoped shared knowledge and are eligible for all agents only when the chat uses the same `user_id`.

## Registry

Everything can be looked up by type and name:

```python
from core.contracts.agent import Agent
from core.contracts.skills import SkillDefinition
from core.contracts.tools import ToolDefinition
from core.registry import Register

agent = Register.get(Agent, "My Agent")
utc_tool = Register.get(ToolDefinition, "get_current_utc_time")
support_skill = Register.get(SkillDefinition, "support.triage")
```

## Runtime Discovery

Discovery is separate from registry:

- `core/discovery.py` loads skill files from `workspace/skills/` and modules from `workspace/tools/` and `workspace/agents/`
- skill ids come from the file path under `workspace/skills/`
- agent ids come from the module path under `workspace/agents/`
- tool modules are loaded first so agent definitions can reference shared tools by name
- `core/platform.py` refreshes discovery, updates registry, and rebuilds runtimes as needed
- `core/registry.py` remains a pure typed registry

For the full platform breakdown, use [core/README.md](./core/README.md).

## API Entrypoint

`api.py` is the local interaction entrypoint for agents (programmatic + CLI).

CLI examples:

```bash
python3 -m api list
python3 -m api catalog
python3 -m api chat "summarize the refund policy"
python3 -m api repl
```

Programmatic examples:

```python
from api import api

agents = api.list_agents()
result = await api.chat(message="Hello", agent_id=None)
streamed_agent, session_id, events = await api.stream_chat_events(
    message="Hello",
    agent_id=None,
    stream=True,
)
```

`stream=True` emits incremental `assistant_delta` events as the answer is generated.
`stream=False` buffers the answer text and emits only the final `assistant_message`, while
tool/progress events still stream live.

## Verification

```bash
uv run python -m pytest
```

## VS Code Related Tests

The workspace now supports two test controllers:

- the normal Python test controller, configured for `pytest`
- a separate `Related Tests` controller driven by source-file metadata

Related test metadata lives at the top of a source file:

```python
"""
Tests:
- tests/core/test_guardrails.py
- tests/core/contracts/test_execution.py
"""
```

The `Related Tests` controller keeps all test files under [`tests/`](./tests) and resolves only the declared files for the selected source module. Test execution still uses `pytest`, which will collect the existing `unittest.TestCase` suites. The workspace settings point VS Code at `.venv/bin/python` so both the Python extension and the related-test controller use the same interpreter by default.

The main Testing-pane refresh remains global. To refresh one selected module in the related-tests tree, use `Refresh Related Tests` on that source item.

To install the local VS Code extension source into your user extensions directory:

```bash
./scripts/install-related-tests-extension.sh
```

The extension source lives in [`vscode-related-tests/`](./vscode-related-tests), and its metadata helper lives in [`vscode-related-tests/python/related_tests_metadata.py`](./vscode-related-tests/python/related_tests_metadata.py).
