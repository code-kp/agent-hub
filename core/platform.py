"""
Tests:
- tests/core/test_platform.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from dotenv import load_dotenv

from core.discovery import DiscoveryService
from core.contracts.agent import Agent
from core.execution import AgentRecord, create_agent_runtime
from core.contracts.skills import SkillDefinition
from core.registry import Register
from core.skills.uploads import create_uploaded_skill


class AgentPlatform:
    """Main platform runtime facade: discovery + registry + agent execution."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        load_dotenv(self.workspace_root.parent / ".env")
        self.discovery = DiscoveryService(self.workspace_root)
        self._records: Dict[str, AgentRecord] = {}
        self._runtimes: Dict[str, Any] = {}
        self.refresh()

    def refresh(self) -> None:
        self.discovery.discover_skills()
        discovered = self.discovery.discover_agents()
        if not discovered:
            raise RuntimeError(
                "No agent modules were discovered under workspace path: {path}".format(
                    path=self.workspace_root
                )
            )

        Register.clear(Agent)
        for item in discovered.values():
            Register.register(
                Agent, item.definition.name, item.definition, overwrite=True
            )

        records: Dict[str, AgentRecord] = {}
        for agent_id, item in discovered.items():
            records[agent_id] = AgentRecord(
                agent_id=agent_id,
                module_name=item.module_name,
                agent_name=item.definition.name,
                project_name=item.project_name,
                project_root=item.project_root,
                fingerprint=item.fingerprint,
            )

        removed_ids = set(self._runtimes.keys()) - set(records.keys())
        for removed_id in removed_ids:
            self._runtimes.pop(removed_id, None)

        for agent_id, record in records.items():
            previous = self._records.get(agent_id)
            if previous != record or agent_id not in self._runtimes:
                self._runtimes[agent_id] = create_agent_runtime(record)

        self._records = records

    def resolve_runtime(self, agent_id: Optional[str]) -> tuple[str, Any]:
        self.refresh()
        resolved_agent = agent_id or sorted(self._records.keys())[0]
        runtime = self._runtimes.get(resolved_agent)
        if runtime is None:
            raise KeyError(
                "Unknown agent id: {agent_id}".format(agent_id=resolved_agent)
            )
        return resolved_agent, runtime

    @property
    def default_agent_id(self) -> str:
        self.refresh()
        return sorted(self._records.keys())[0]

    def catalog(self) -> Dict[str, Any]:
        self.refresh()
        return {
            "default_agent_id": sorted(self._records.keys())[0],
            "agents": self.list_agents(refresh=False),
            "tree": self.agent_tree(refresh=False),
        }

    def refresh_skills(self) -> Dict[str, Any]:
        discovered = self.discovery.discover_skills()
        return {
            "count": len(discovered),
            "skills": [
                {
                    "id": item.skill_id,
                    "source": item.source,
                    "class": item.definition.skill_class,
                    "title": item.definition.title,
                    "summary": item.definition.summary,
                }
                for item in sorted(
                    discovered.values(), key=lambda value: value.skill_id
                )
            ],
        }

    def list_agents(self, refresh: bool = True) -> List[Dict[str, str]]:
        if refresh:
            self.refresh()
        agents = []
        for agent_id, record in sorted(self._records.items(), key=lambda pair: pair[0]):
            definition = Register.get(Agent, record.agent_name)
            agents.append(
                {
                    "id": agent_id,
                    "name": definition.name,
                    "description": definition.description,
                    "module": record.module_name,
                    "project": record.project_name,
                }
            )
        return agents

    def agent_tree(self, refresh: bool = True) -> List[Dict[str, Any]]:
        if refresh:
            self.refresh()
        root: Dict[str, Any] = {}
        for agent_id, record in sorted(self._records.items(), key=lambda pair: pair[0]):
            definition = Register.get(Agent, record.agent_name)
            parts = agent_id.split(".")
            cursor = root
            for namespace in parts[:-1]:
                node = cursor.setdefault(
                    namespace,
                    {
                        "type": "namespace",
                        "name": namespace,
                        "children": {},
                    },
                )
                cursor = node["children"]

            leaf = parts[-1]
            cursor[leaf] = {
                "type": "agent",
                "id": agent_id,
                "name": definition.name,
                "description": definition.description,
            }

        def flatten(children_map: Dict[str, Any]) -> List[Dict[str, Any]]:
            nodes = []
            for key in sorted(children_map.keys()):
                node = children_map[key]
                if node["type"] == "namespace":
                    nodes.append(
                        {
                            "type": "namespace",
                            "name": node["name"],
                            "children": flatten(node["children"]),
                        }
                    )
                else:
                    nodes.append(
                        {
                            "type": "agent",
                            "id": node["id"],
                            "name": node["name"],
                            "description": node["description"],
                        }
                    )
            return nodes

        return flatten(root)

    async def stream_chat(
        self,
        *,
        agent_id: Optional[str],
        message: str,
        user_id: str,
        session_id: Optional[str],
        history: Optional[Sequence[Mapping[str, Any]]] = None,
        stream: bool = True,
    ):
        resolved_agent, runtime = self.resolve_runtime(agent_id)
        active_session_id, event_stream = await runtime.stream_chat(
            message=message,
            user_id=user_id,
            session_id=session_id,
            history=history,
            stream=stream,
        )
        return resolved_agent, active_session_id, event_stream

    def upload_skill_markdown(
        self,
        *,
        file_name: str,
        content: str,
        uploader_id: str,
        namespace: str = "",
    ) -> Dict[str, Any]:
        definition = create_uploaded_skill(
            skills_root=self.workspace_root / "skills",
            file_name=file_name,
            content=content,
            uploader_id=uploader_id,
            namespace=namespace,
        )
        self.refresh_skills()
        return self._serialize_skill(definition)

    def _serialize_skill(self, definition: SkillDefinition) -> Dict[str, Any]:
        return {
            "id": definition.id,
            "source": definition.source,
            "path": str(definition.path),
            "title": definition.title,
            "class": definition.skill_class,
            "summary": definition.summary,
        }
