# Workspace

Everything contributors need lives here:

- `agents/` for agent modules
- `tools/` for shared tool modules
- `skills/` for markdown skills

Rules:

- Agent ids come from the directory hierarchy under `agents/`
- Tool modules are loaded before agent modules, so agents can reference tools by name
- Skills are shared content under `skills/`; agents can point `skills_dir` at a subdirectory like `general` or `support`

Example:

```python
from core.interfaces.agent import AgentModule, register_agent_class


@register_agent_class
class MyAgent(AgentModule):
    name = "My Agent"
    description = "What it does"
    system_prompt = "How it should behave"
    tools = ("get_current_utc_time", "search_skills")
    skills_dir = "general"
```
