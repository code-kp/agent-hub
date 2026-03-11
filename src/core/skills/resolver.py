"""
Tests:
- tests/core/skills/test_resolver.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from core.contracts.skills import SkillDefinition, ensure_skill_ids
from core.skills.store import SkillChunk, SkillStore
from core.skills.uploads import build_user_upload_scope


@dataclass(frozen=True)
class ResolvedSkillContext:
    behavior: tuple[SkillDefinition, ...] = ()
    knowledge: tuple[SkillDefinition, ...] = ()
    chunks: tuple[SkillChunk, ...] = ()

    @property
    def all_skills(self) -> tuple[SkillDefinition, ...]:
        ordered: List[SkillDefinition] = []
        seen = set()
        for skill in [*self.behavior, *self.knowledge]:
            if skill.id in seen:
                continue
            seen.add(skill.id)
            ordered.append(skill)
        return tuple(ordered)

    @property
    def is_empty(self) -> bool:
        return not self.behavior and not self.knowledge and not self.chunks


class SkillResolver:
    def __init__(self, store: SkillStore) -> None:
        self.store = store

    def resolve(
        self,
        *,
        query: str,
        user_id: str,
        behavior_ids: Sequence[str] = (),
        knowledge_ids: Sequence[str] = (),
        max_auto_skills: int = 3,
        max_chunks: int = 4,
        max_chunk_chars: int = 1600,
    ) -> ResolvedSkillContext:
        self.store.refresh()
        behavior_skill_ids = set(ensure_skill_ids(behavior_ids))
        knowledge_skill_ids = set(ensure_skill_ids(knowledge_ids))

        behavior_skills = self._resolve_explicit_skills(
            behavior_skill_ids, expected_class="behavior"
        )
        knowledge_candidates = self._resolve_explicit_skills(
            knowledge_skill_ids, expected_class="knowledge"
        )
        knowledge_candidates.extend(self._resolve_user_upload_knowledge(user_id))

        behavior_skill_set = {skill.id for skill in behavior_skills}
        scored_candidates: List[tuple[float, SkillDefinition]] = []
        for skill in knowledge_candidates:
            if skill.id in behavior_skill_set:
                continue
            score = self._score_skill(skill, query)
            if score <= 0:
                continue
            scored_candidates.append((score, skill))

        scored_candidates.sort(key=lambda item: (-item[0], item[1].id))
        selected_skills = [skill for _, skill in scored_candidates[:max_auto_skills]]
        selected_ids = {skill.id for skill in selected_skills}
        chunk_skill_ids = list(behavior_skill_set | selected_ids)
        chunks = self.store.select_relevant_chunks(
            query=query,
            max_chunks=max_chunks,
            max_chars=max_chunk_chars,
            skill_ids=chunk_skill_ids,
        )
        return ResolvedSkillContext(
            behavior=tuple(behavior_skills),
            knowledge=tuple(selected_skills),
            chunks=tuple(chunks),
        )

    def _resolve_explicit_skills(
        self,
        skill_ids: set[str],
        *,
        expected_class: str,
    ) -> list[SkillDefinition]:
        resolved: list[SkillDefinition] = []
        seen = set()
        for skill_id in skill_ids:
            skill = self.store.get_skill(skill_id)
            if skill is None or skill.id in seen:
                continue
            if skill.skill_class != expected_class:
                continue
            resolved.append(skill)
            seen.add(skill.id)
        return resolved

    def _resolve_user_upload_knowledge(self, user_id: str) -> list[SkillDefinition]:
        upload_scope = build_user_upload_scope(user_id)
        resolved: list[SkillDefinition] = []
        for skill in self.store.list_skills():
            if skill.skill_class != "knowledge":
                continue
            if skill.id == upload_scope or skill.id.startswith(upload_scope + "."):
                resolved.append(skill)
        return resolved

    def _score_skill(self, skill: SkillDefinition, query: str) -> float:
        query_tokens = self.store._tokenize(query)  # intentional shared normalization
        if not query_tokens:
            return 0.0

        metadata_tokens = self.store._tokenize(
            "{title} {summary} {body}".format(
                title=skill.title,
                summary=skill.summary,
                body=skill.body[:800],
            )
        )
        if not metadata_tokens:
            return 0.0

        overlap = 0.0
        metadata_token_set = set(metadata_tokens)
        for token in query_tokens:
            if token in metadata_token_set:
                overlap += 1.0

        query_text = query.lower()
        title_bonus = (
            1.5 if any(token in skill.title.lower() for token in query_tokens) else 0.0
        )
        summary_bonus = (
            1.0 if query_text and query_text in skill.summary.lower() else 0.0
        )
        phrase_bonus = 1.0 if query_text and query_text in skill.body.lower() else 0.0

        return overlap + title_bonus + summary_bonus + phrase_bonus


def describe_resolved_skill_context(context: ResolvedSkillContext) -> str:
    if context.is_empty:
        return "No shared skills were selected for this request."

    parts: List[str] = []
    if context.behavior:
        labels = ", ".join(skill.id for skill in context.behavior)
        parts.append(
            "Loaded {count} behavior skill(s): {labels}.".format(
                count=len(context.behavior),
                labels=labels,
            )
        )
    if context.knowledge:
        labels = ", ".join(skill.id for skill in context.knowledge)
        parts.append(
            "Matched {count} knowledge skill(s): {labels}.".format(
                count=len(context.knowledge),
                labels=labels,
            )
        )
    if context.chunks:
        parts.append(
            "Prepared {count} detailed excerpt(s) for model context.".format(
                count=len(context.chunks)
            )
        )
    return " ".join(parts)


def serialize_resolved_skills(context: ResolvedSkillContext) -> List[Dict[str, str]]:
    items = []
    behavior_ids = {skill.id for skill in context.behavior}
    for skill in context.all_skills:
        items.append(
            {
                "id": skill.id,
                "title": skill.title,
                "class": skill.skill_class,
                "summary": skill.summary,
                "role": "behavior" if skill.id in behavior_ids else "selected",
                "source": skill.source,
            }
        )
    return items
