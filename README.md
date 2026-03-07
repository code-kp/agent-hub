# Agent Platform

Framework-style platform for creating and running custom agents with:

- strict separation of `core/` platform runtime and `workspace/` creator content
- one shared workspace for agents, tools, and skills
- class-based agent authoring API
- metadata-driven skill discovery and scoped skill resolution
- global typed registry (`Register.get(Type, name)`)
- runtime discovery of tools and agents on every API interaction
- streaming chat/tool/progress events to the UI

## Documentation

- [Core architecture](./core/README.md)
  - what each core module does
  - where discovery, runtime, policy, skill resolution, and streaming logic belong
- [Workspace authoring](./workspace/README.md)
  - how to define agents, tools, and skills in the shared workspace

## Structure

```text
core/
  contracts/
  skills/
  stream/
  policies/
  discovery.py
  platform.py
  registry.py
  runtime.py
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

@register_agent_class
class MyAgent(AgentModule):
    name = "My Agent"
    description = "What it does"
    system_prompt = "How it should behave"
    tools = ("get_current_utc_time", "search_skills")  # tool names from global registry
    skill_scopes = ("general", "support")
    always_on_skills = ("general.persona",)
```

Best practice:
- keep `system_prompt` focused on behavior and output style
- keep domain knowledge in skills, not in the prompt
- use `skill_scopes` for what the agent is allowed to use
- use `always_on_skills` only for small persona/policy instructions

## Authoring Tools

Put tools under `workspace/tools/...` and define them with `@tool(...)`.
All tools are loaded before agents, so any agent can reference any tool by name.

Example:

```python
from core.contracts.tools import current_progress, tool

@tool(
    description="Return UTC time.",
    category="time",
    use_when=("The request asks for current time or date.",),
    returns="A UTC timestamp in ISO 8601 format.",
)
def get_current_utc_time() -> dict:
    progress = current_progress()
    progress.think("Checking the current time", detail="Confirming the current UTC time.")
    ...
```

Best practice:
- fill in tool metadata well enough that the runtime and model can make good decisions
- emit `progress.think(...)` for user-facing narration
- emit `progress.debug(...)` for developer detail
- keep hard routing rules out of the tool itself; put those in `core/policies/`

## Authoring Skills

Put markdown skills anywhere under `workspace/skills/...`.

Examples:

- `workspace/skills/general/product.md`
- `workspace/skills/support/triage.md`

Skill ids come from the directory hierarchy under `workspace/skills/`:

- `workspace/skills/general/product.md` -> `general.product`
- `workspace/skills/support/triage.md` -> `support.triage`

Each skill file should start with frontmatter:

```md
---
title: Support Triage Workflow
type: workflow
summary: First-response and escalation workflow for support issues.
tags: [support, triage, escalation]
triggers: [issue, production, troubleshoot]
mode: auto
priority: 80
requires_tools: [search_skills]
---
```

Supported skill `type` values:

- `persona`
- `policy`
- `workflow`
- `knowledge`

Supported `mode` values:

- `always_on`
- `auto`
- `manual`

Best practice:
- `persona`: short instructions that shape behavior
- `policy`: rules, constraints, boundaries
- `workflow`: step-by-step procedures
- `knowledge`: product docs, FAQs, references, notes
- keep one skill focused on one concern instead of mixing everything into one file

Agents now declare `skill_scopes` instead of pointing at one folder. The runtime:

- filters skills by scope
- always loads `always_on` skills in that scope, plus any explicit `always_on_skills`
- chooses additional skills per request using metadata + lexical matching
- injects summaries first and only adds detailed excerpts for the top matches

The shared skill tools (`search_skills`, `list_skill_files`, `read_skill_file`) still exist as fallback/debug tools over the full `workspace/skills/` tree.

### Uploading Markdown As Skills

Use the backend upload endpoint to turn any markdown file into a skill:

```bash
curl -X POST http://127.0.0.1:8000/api/skills/upload \
  -F "file=@/path/to/refund-faq.md" \
  -F "user_id=browser-user" \
  -F "namespace=billing" \
  -F "tags=billing,refund" \
  -F "triggers=refund,annual plan"
```

Uploaded files are stored under `workspace/skills/uploads/...` and default to `type=knowledge`, `mode=auto`.

That is the recommended default:

- use `knowledge` for uploaded docs, notes, guides, FAQs, release notes, and product references
- use `persona` only for short, stable instructions that should shape how an agent behaves

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
```

## Verification

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```
