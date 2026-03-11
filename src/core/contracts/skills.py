"""
Tests:
- tests/core/contracts/test_skills.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from core.registry import Register


VALID_SKILL_CLASSES = frozenset({"behavior", "knowledge"})


@dataclass(frozen=True)
class SkillDefinition:
    """Normalized skill asset discovered from workspace markdown."""

    id: str
    source: str
    path: Path
    title: str
    summary: str
    skill_class: str = "knowledge"
    body: str = ""

    @property
    def is_behavior(self) -> bool:
        return self.skill_class == "behavior"

    @property
    def is_knowledge(self) -> bool:
        return self.skill_class == "knowledge"


def normalize_skill_id(value: str) -> str:
    text = str(value or "").strip()
    return text.replace("/", ".")


def ensure_skill_ids(skill_ids: Optional[Sequence[str]]) -> tuple[str, ...]:
    values = []
    seen = set()
    for raw in list(skill_ids or ()):
        normalized = normalize_skill_id(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        values.append(normalized)
    return tuple(values)


def register_skill(
    skill_definition: SkillDefinition, *, name: Optional[str] = None
) -> SkillDefinition:
    register_name = normalize_skill_id(name or skill_definition.id)
    if not register_name:
        raise ValueError("Skill id must be non-empty.")
    Register.register(SkillDefinition, register_name, skill_definition, overwrite=True)
    return skill_definition


def register_skills(
    skill_definitions: Iterable[SkillDefinition],
) -> List[SkillDefinition]:
    registered: List[SkillDefinition] = []
    for item in skill_definitions:
        registered.append(register_skill(item))
    return registered
