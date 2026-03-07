# Agent Platform

Framework-style platform for creating and running custom agents with:

- strict separation of `core/` platform runtime and `workspace/` creator content
- one shared workspace for agents, tools, and skills
- class-based agent authoring API
- global typed registry (`Register.get(Type, name)`)
- runtime discovery of tools and agents on every API interaction
- streaming chat/tool/progress events to the UI

## Structure

```text
core/
  interfaces/
    agent.py
    tools.py
  discovery.py
  platform.py
  progress.py
  registry.py
  runtime.py
  skill_store.py
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
from core.interfaces.agent import AgentModule, register_agent_class

@register_agent_class
class MyAgent(AgentModule):
    name = "My Agent"
    description = "What it does"
    system_prompt = "How it should behave"
    tools = ("get_current_utc_time", "search_skills")  # tool names from global registry
    skills_dir = "general"  # resolves to workspace/skills/general
```

## Authoring Tools

Put tools under `workspace/tools/...` and define them with `@tool(...)`.
All tools are loaded before agents, so any agent can reference any tool by name.

Example:

```python
from core.interfaces.tools import tool

@tool(description="Return UTC time")
def get_current_utc_time() -> dict:
    ...
```

## Authoring Skills

Put markdown skills anywhere under `workspace/skills/...`.

Examples:

- `workspace/skills/general/product.md`
- `workspace/skills/support/triage.md`

Agents can point `skills_dir` at a subdirectory such as `general` or `support`.
The shared skill tools (`search_skills`, `list_skill_files`, `read_skill_file`) search the full `workspace/skills/` tree.

## Registry

Everything can be looked up by type and name:

```python
from core.interfaces.agent import Agent
from core.interfaces.tools import ToolDefinition
from core.registry import Register

agent = Register.get(Agent, "My Agent")
utc_tool = Register.get(ToolDefinition, "get_current_utc_time")
```

## Runtime Discovery

Discovery is separate from registry:

- `core/discovery.py` loads modules from `workspace/tools/` and `workspace/agents/`
- agent ids come from the module path under `workspace/agents/`
- tool modules are loaded first so agent definitions can reference shared tools by name
- `core/platform.py` refreshes discovery, updates registry, and rebuilds runtimes as needed
- `core/registry.py` remains a pure typed registry

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
