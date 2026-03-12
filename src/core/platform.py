"""
Tests:
- tests/core/test_platform.py
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from dotenv import dotenv_values

from core.discovery import DiscoveryService
from core.contracts.agent import Agent, normalize_runtime_mode
from core.contracts.tools import ensure_tools
from core.execution import AgentRecord, create_agent_runtime
from core.execution.smart.runtime import (
    SMART_AGENT_DESCRIPTION,
    SMART_AGENT_ID,
    SMART_AGENT_NAME,
    SmartAgentRuntime,
)
from core.contracts.skills import SkillDefinition
from core.registry import Register
from core.skills.uploads import create_uploaded_skill


class AgentPlatform:
    """Main platform runtime facade: discovery + registry + agent execution."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self._env_path = self._resolve_env_path()
        self._loaded_env_keys: Dict[str, Optional[str]] = {}
        self._last_dotenv_values: Dict[str, str] = {}
        self.discovery = DiscoveryService(self.workspace_root)
        self._records: Dict[str, AgentRecord] = {}
        self._runtimes: Dict[tuple[str, str, str], Any] = {}
        self.refresh()

    def _resolve_env_path(self) -> Path:
        for directory in self.workspace_root.parents:
            candidate = directory / ".env"
            if candidate.is_file():
                return candidate
        return self.workspace_root.parent / ".env"

    def refresh(self) -> None:
        env_changed = self._sync_workspace_env()
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
        definitions: Dict[str, Agent] = {}
        for agent_id, item in discovered.items():
            definitions[agent_id] = item.definition
            records[agent_id] = AgentRecord(
                agent_id=agent_id,
                module_name=item.module_name,
                agent_name=item.definition.name,
                project_name=item.project_name,
                project_root=item.project_root,
                fingerprint=item.fingerprint,
            )

        removed_runtime_keys = [
            key for key in self._runtimes.keys() if key[0] not in records
        ]
        for runtime_key in removed_runtime_keys:
            self._runtimes.pop(runtime_key, None)

        if env_changed:
            self._runtimes.clear()

        for agent_id, record in records.items():
            previous = self._records.get(agent_id)
            if previous != record:
                stale_keys = [
                    key for key in self._runtimes.keys() if key[0] == agent_id
                ]
                for runtime_key in stale_keys:
                    self._runtimes.pop(runtime_key, None)

            default_mode = normalize_runtime_mode(definitions[agent_id].runtime_mode)
            runtime_key = (agent_id, default_mode, "")
            if runtime_key not in self._runtimes:
                self._runtimes[runtime_key] = create_agent_runtime(
                    record,
                    runtime_mode=default_mode,
                )

        self._records = records

    def _sync_workspace_env(self) -> bool:
        self._env_path = self._resolve_env_path()
        next_values = {
            key: value
            for key, value in dotenv_values(self._env_path).items()
            if key and value is not None
        }
        if next_values == self._last_dotenv_values:
            return False

        removed_keys = set(self._last_dotenv_values.keys()) - set(next_values.keys())
        for key in removed_keys:
            if key not in self._loaded_env_keys:
                continue
            original_value = self._loaded_env_keys.pop(key)
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value

        for key, value in next_values.items():
            if key in self._loaded_env_keys:
                os.environ[key] = value
                continue
            existing_value = os.environ.get(key)
            if existing_value not in (None, ""):
                continue
            self._loaded_env_keys[key] = None
            os.environ[key] = value

        self._last_dotenv_values = next_values
        return True

    def resolve_runtime(
        self,
        agent_id: Optional[str],
        mode: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> tuple[str, str, Any]:
        self.refresh()
        resolved_agent = agent_id or sorted(self._records.keys())[0]
        requested_model_name = str(model_name or "").strip()

        if resolved_agent == SMART_AGENT_ID:
            resolved_mode = normalize_runtime_mode(mode or "direct")
            if resolved_mode != "direct":
                raise ValueError(
                    "The coordinator only supports direct runtime selection."
                )
            runtime_key = (resolved_agent, resolved_mode, requested_model_name)
            runtime = self._runtimes.get(runtime_key)
            if runtime is None:
                runtime = SmartAgentRuntime(
                    self,
                    model_name_override=requested_model_name or None,
                )
                self._runtimes[runtime_key] = runtime
            return resolved_agent, resolved_mode, runtime

        record = self._records.get(resolved_agent)
        if record is None:
            raise KeyError(
                "Unknown agent id: {agent_id}".format(agent_id=resolved_agent)
            )
        definition = Register.get(Agent, record.agent_name)
        resolved_mode = normalize_runtime_mode(mode or definition.runtime_mode)

        if resolved_mode == "orchestrated" and not definition.orchestration_configured:
            raise ValueError(
                "Orchestration is not configured for agent: {agent_id}".format(
                    agent_id=resolved_agent
                )
            )

        runtime_key = (resolved_agent, resolved_mode, requested_model_name)
        runtime = self._runtimes.get(runtime_key)
        if runtime is None:
            runtime = create_agent_runtime(
                record,
                runtime_mode=resolved_mode,
                model_name=requested_model_name or None,
            )
            self._runtimes[runtime_key] = runtime
        return resolved_agent, resolved_mode, runtime

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

    def list_agents(self, refresh: bool = True) -> List[Dict[str, Any]]:
        if refresh:
            self.refresh()
        agents = [self._smart_agent_entry()]
        for agent_id, record in sorted(self._records.items(), key=lambda pair: pair[0]):
            definition = Register.get(Agent, record.agent_name)
            runtime_modes = ["direct"]
            if definition.orchestration_configured:
                runtime_modes.append("orchestrated")
            agents.append(
                {
                    "id": agent_id,
                    "name": definition.name,
                    "description": definition.description,
                    "module": record.module_name,
                    "project": record.project_name,
                    "default_mode": normalize_runtime_mode(definition.runtime_mode),
                    "runtime_modes": runtime_modes,
                    "orchestration_configured": definition.orchestration_configured,
                }
            )
        return agents

    def agent_tree(self, refresh: bool = True) -> List[Dict[str, Any]]:
        if refresh:
            self.refresh()
        root: Dict[str, Any] = {
            SMART_AGENT_ID: {
                "type": "agent",
                "id": SMART_AGENT_ID,
                "name": SMART_AGENT_NAME,
                "description": SMART_AGENT_DESCRIPTION,
            }
        }
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
            for key in sorted(
                children_map.keys(),
                key=lambda item: (item != SMART_AGENT_ID, item),
            ):
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

    def routing_candidates(self, refresh: bool = True) -> List[Dict[str, Any]]:
        if refresh:
            self.refresh()

        candidates: List[Dict[str, Any]] = []
        for agent_id, record in sorted(self._records.items(), key=lambda pair: pair[0]):
            definition = Register.get(Agent, record.agent_name)
            runtime_modes = ["direct"]
            if definition.orchestration_configured:
                runtime_modes.append("orchestrated")
            candidates.append(
                {
                    "id": agent_id,
                    "name": definition.name,
                    "description": definition.description,
                    "default_mode": normalize_runtime_mode(definition.runtime_mode),
                    "runtime_modes": runtime_modes,
                    "behavior": list(definition.behavior),
                    "knowledge": list(definition.knowledge),
                    "tools": [tool.name for tool in ensure_tools(definition.tools)],
                    "system_prompt": definition.system_prompt,
                }
            )
        return candidates

    async def stream_chat(
        self,
        *,
        agent_id: Optional[str],
        team_agent_ids: Optional[Sequence[str]],
        mode: Optional[str],
        model_name: Optional[str],
        message: str,
        user_id: str,
        session_id: Optional[str],
        conversation_id: Optional[str] = None,
        history: Optional[Sequence[Mapping[str, Any]]] = None,
        stream: bool = True,
    ):
        resolved_agent, resolved_mode, runtime = self.resolve_runtime(
            agent_id,
            mode=mode,
            model_name=model_name,
        )
        runtime_kwargs = {
            "message": message,
            "user_id": user_id,
            "session_id": session_id,
            "conversation_id": conversation_id,
            "history": history,
            "stream": stream,
        }
        if resolved_agent == SMART_AGENT_ID:
            runtime_kwargs["team_agent_ids"] = list(team_agent_ids or [])

        active_session_id, event_stream = await runtime.stream_chat(**runtime_kwargs)
        return resolved_agent, resolved_mode, active_session_id, event_stream

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
        from core.retrieval.index import LocalEmbeddingIndex

        LocalEmbeddingIndex(
            self.workspace_root.parent.parent / ".embeddings"
        ).mark_dirty(
            "skills",
            key=definition.id,
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

    def _smart_agent_entry(self) -> Dict[str, Any]:
        return {
            "id": SMART_AGENT_ID,
            "name": SMART_AGENT_NAME,
            "description": SMART_AGENT_DESCRIPTION,
            "module": "core.execution.smart",
            "project": "system",
            "default_mode": "direct",
            "runtime_modes": ["direct"],
            "orchestration_configured": False,
            "virtual": True,
        }
