from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentRecord:
    agent_id: str
    module_name: str
    agent_name: str
    project_name: str
    project_root: Path
    fingerprint: str
