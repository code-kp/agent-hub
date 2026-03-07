from __future__ import annotations

import importlib
import hashlib
import inspect
import pkgutil
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from core.contracts.agent import Agent, AgentModule
from core.contracts.skills import SkillDefinition, register_skill
from core.contracts.tools import ToolDefinition
from core.registry import Register
from core.skills.parser import parse_skill_file


SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    text = value.lower().strip()
    text = SLUG_RE.sub("-", text)
    text = text.strip("-")
    return text or "agent"


def _agent_fingerprint(definition: Agent) -> str:
    tool_markers = ",".join(sorted(_tool_fingerprint(tool) for tool in definition.tools))
    return "|".join(
        [
            definition.name,
            definition.description,
            definition.system_prompt,
            ",".join(sorted(str(item) for item in definition.skill_scopes)),
            ",".join(sorted(str(item) for item in definition.always_on_skills)),
            definition.skills_dir or "",
            definition.model or "",
            tool_markers,
        ]
    )


def _tool_fingerprint(tool: ToolDefinition) -> str:
    handler = tool.handler
    handler_module = getattr(handler, "__module__", "")
    handler_name = getattr(handler, "__qualname__", getattr(handler, "__name__", "handler"))
    source = ""
    try:
        source = inspect.getsource(handler)
    except (OSError, TypeError):  # pragma: no cover
        source = ""
    digest = hashlib.sha1(source.encode("utf-8"), usedforsecurity=False).hexdigest()
    return "|".join(
        [
            tool.name,
            tool.description,
            tool.category,
            ",".join(tool.use_when),
            ",".join(tool.avoid_when),
            tool.returns,
            str(tool.requires_current_data),
            ",".join(tool.follow_up_tools),
            handler_module,
            handler_name,
            digest,
        ]
    )


@dataclass(frozen=True)
class DiscoveredAgent:
    agent_id: str
    module_name: str
    project_name: str
    project_root: Path
    definition: Agent
    fingerprint: str


@dataclass(frozen=True)
class DiscoveredSkill:
    skill_id: str
    source: str
    definition: SkillDefinition
    fingerprint: str


class DiscoveryService:
    """Discover tool and agent modules from the shared workspace at runtime."""

    def __init__(self, workspace_root: Path, workspace_package: str = "workspace") -> None:
        self.workspace_root = workspace_root
        self.workspace_package = workspace_package

    def discover_agents(self) -> Dict[str, DiscoveredAgent]:
        self._prepare_import_path()
        self._load_tool_modules()

        discovered: Dict[str, DiscoveredAgent] = {}
        for module_name, agent_namespace in self._namespace_modules("agents"):
            module = self._load_module(module_name)
            definitions = self._collect_module_agents(module)
            if not definitions:
                continue

            base_agent_id = agent_namespace or "index"
            namespace_root = base_agent_id.split(".", 1)[0] if base_agent_id else "workspace"

            for index, definition in enumerate(definitions):
                agent_id = base_agent_id
                if len(definitions) > 1:
                    agent_id = "{base}.{slug}".format(base=base_agent_id, slug=_slugify(definition.name))
                    if index > 0 and agent_id in discovered:
                        agent_id = "{base}-{index}".format(base=agent_id, index=index + 1)

                if agent_id in discovered:
                    raise RuntimeError(
                        "Duplicate agent id discovered during runtime discovery: {agent_id}".format(
                            agent_id=agent_id
                        )
                    )

                discovered[agent_id] = DiscoveredAgent(
                    agent_id=agent_id,
                    module_name=module_name,
                    project_name=namespace_root,
                    project_root=self.workspace_root,
                    definition=definition,
                    fingerprint=_agent_fingerprint(definition),
                )

        return discovered

    def discover_skills(self) -> Dict[str, DiscoveredSkill]:
        skills_root = self.workspace_root / "skills"
        Register.clear(SkillDefinition)
        if not skills_root.exists():
            return {}

        discovered: Dict[str, DiscoveredSkill] = {}
        for path in sorted(skills_root.rglob("*.md")):
            definition = parse_skill_file(path, skills_root)
            if definition.id in discovered:
                raise RuntimeError(
                    "Duplicate skill id discovered during runtime discovery: {skill_id}".format(
                        skill_id=definition.id
                    )
                )
            register_skill(definition)
            discovered[definition.id] = DiscoveredSkill(
                skill_id=definition.id,
                source=definition.source,
                definition=definition,
                fingerprint=_skill_fingerprint(definition),
            )
        return discovered

    def _prepare_import_path(self) -> None:
        if not self.workspace_root.exists():
            return
        root_parent = str(self.workspace_root.parent)
        if root_parent not in sys.path:
            sys.path.insert(0, root_parent)
        importlib.invalidate_caches()

    def _load_tool_modules(self) -> None:
        Register.clear(ToolDefinition)
        for module_name, _ in self._namespace_modules("tools"):
            self._load_module(module_name)

    def _namespace_modules(self, component: str) -> List[Tuple[str, str]]:
        component_root = self.workspace_root / component
        if not component_root.exists():
            return []

        package_name = "{workspace}.{component}".format(
            workspace=self.workspace_package,
            component=component,
        )
        package = self._load_module(package_name)
        module_names = [package_name]

        package_path = getattr(package, "__path__", None)
        if package_path is not None:
            prefix = "{pkg}.".format(pkg=package_name)
            for module_info in pkgutil.walk_packages(package_path, prefix=prefix):
                module_names.append(module_info.name)

        modules: List[Tuple[str, str]] = []
        seen: Set[str] = set()
        for module_name in sorted(module_names):
            if module_name in seen:
                continue
            seen.add(module_name)
            if module_name == package_name:
                namespace = ""
            else:
                namespace = module_name[len(package_name) + 1 :]
            modules.append((module_name, namespace))
        return modules

    def _load_module(self, module_name: str):
        if module_name in sys.modules:
            return importlib.reload(sys.modules[module_name])
        return importlib.import_module(module_name)

    def _collect_module_agents(self, module: Any) -> List[Agent]:
        collected: List[Agent] = []
        seen_names = set()

        def add_candidate(candidate: Any) -> None:
            if not isinstance(candidate, Agent):
                return
            if candidate.name in seen_names:
                return
            seen_names.add(candidate.name)
            collected.append(candidate)

        add_candidate(getattr(module, "agent", None))

        module_agents = getattr(module, "agents", None)
        if isinstance(module_agents, (list, tuple, set)):
            for candidate in module_agents:
                add_candidate(candidate)

        for _, value in inspect.getmembers(module, inspect.isclass):
            if not issubclass(value, AgentModule) or value is AgentModule:
                continue
            add_candidate(getattr(value, "__agent_definition__", None))

        return collected


def _skill_fingerprint(definition: SkillDefinition) -> str:
    digest = hashlib.sha1(definition.body.encode("utf-8"), usedforsecurity=False).hexdigest()
    return "|".join(
        [
            definition.id,
            definition.source,
            definition.title,
            definition.skill_type,
            definition.summary,
            definition.mode,
            str(definition.priority),
            ",".join(definition.tags),
            ",".join(definition.triggers),
            ",".join(definition.requires_tools),
            digest,
        ]
    )
