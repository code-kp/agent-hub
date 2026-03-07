from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from core.registry import Register


VALID_SKILL_TYPES = frozenset({"persona", "policy", "workflow", "knowledge"})
VALID_SKILL_MODES = frozenset({"always_on", "auto", "manual"})


@dataclass(frozen=True)
class SkillDefinition:
    """Normalized skill asset discovered from workspace markdown."""

    id: str
    source: str
    path: Path
    title: str
    skill_type: str
    summary: str
    tags: tuple[str, ...] = ()
    triggers: tuple[str, ...] = ()
    mode: str = "auto"
    priority: int = 50
    requires_tools: tuple[str, ...] = ()
    body: str = ""

    def matches_scope(self, scope: str) -> bool:
        normalized = normalize_skill_scope(scope)
        if not normalized:
            return False
        if normalized == "*":
            return True
        if fnmatchcase(self.id, normalized):
            return True
        if "*" not in normalized and (self.id == normalized or self.id.startswith(normalized + ".")):
            return True
        return False


def normalize_skill_scope(value: str) -> str:
    text = str(value or "").strip()
    return text.replace("/", ".")


def ensure_skill_scopes(scopes: Optional[Sequence[str]]) -> tuple[str, ...]:
    values = []
    seen = set()
    for raw in list(scopes or ()):
        normalized = normalize_skill_scope(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        values.append(normalized)
    return tuple(values)


def ensure_skill_ids(skill_ids: Optional[Sequence[str]]) -> tuple[str, ...]:
    values = []
    seen = set()
    for raw in list(skill_ids or ()):
        normalized = normalize_skill_scope(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        values.append(normalized)
    return tuple(values)


def register_skill(skill_definition: SkillDefinition, *, name: Optional[str] = None) -> SkillDefinition:
    register_name = normalize_skill_scope(name or skill_definition.id)
    if not register_name:
        raise ValueError("Skill id must be non-empty.")
    Register.register(SkillDefinition, register_name, skill_definition, overwrite=True)
    return skill_definition


def register_skills(skill_definitions: Iterable[SkillDefinition]) -> List[SkillDefinition]:
    registered: List[SkillDefinition] = []
    for item in skill_definitions:
        registered.append(register_skill(item))
    return registered

