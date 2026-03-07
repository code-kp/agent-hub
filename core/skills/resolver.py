from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Sequence

from core.contracts.skills import SkillDefinition, ensure_skill_ids, ensure_skill_scopes
from core.skills.store import SkillChunk, SkillStore
from core.skills.uploads import build_user_upload_scope


@dataclass(frozen=True)
class ResolvedSkillContext:
    always_on_skills: tuple[SkillDefinition, ...] = ()
    selected_skills: tuple[SkillDefinition, ...] = ()
    chunks: tuple[SkillChunk, ...] = ()

    @property
    def all_skills(self) -> tuple[SkillDefinition, ...]:
        ordered: List[SkillDefinition] = []
        seen = set()
        for skill in [*self.always_on_skills, *self.selected_skills]:
            if skill.id in seen:
                continue
            seen.add(skill.id)
            ordered.append(skill)
        return tuple(ordered)

    @property
    def is_empty(self) -> bool:
        return not self.always_on_skills and not self.selected_skills and not self.chunks


class SkillResolver:
    def __init__(self, store: SkillStore) -> None:
        self.store = store

    def resolve(
        self,
        *,
        query: str,
        user_id: str,
        skill_scopes: Sequence[str],
        always_on_skill_ids: Sequence[str] = (),
        max_auto_skills: int = 3,
        max_chunks: int = 4,
        max_chunk_chars: int = 1600,
    ) -> ResolvedSkillContext:
        self.store.refresh()
        scopes = ensure_skill_scopes(skill_scopes)
        shared_scopes = ensure_skill_scopes((build_user_upload_scope(user_id),))
        explicit_always_on = set(ensure_skill_ids(always_on_skill_ids))
        allowed_skills = [
            skill
            for skill in self.store.list_skills()
            if (
                not scopes
                or any(skill.matches_scope(scope) for scope in scopes)
                or any(skill.matches_scope(scope) for scope in shared_scopes)
            )
        ]
        if not allowed_skills:
            return ResolvedSkillContext()

        always_on = [
            skill
            for skill in allowed_skills
            if skill.mode == "always_on" or skill.id in explicit_always_on
        ]
        always_on_ids = {skill.id for skill in always_on}

        scored_candidates: List[tuple[float, SkillDefinition]] = []
        for skill in allowed_skills:
            if skill.id in always_on_ids or skill.mode == "manual":
                continue
            score = self._score_skill(skill, query)
            if score <= 0:
                continue
            scored_candidates.append((score, skill))

        scored_candidates.sort(
            key=lambda item: (-item[0], -item[1].priority, item[1].id)
        )
        selected_skills = [skill for _, skill in scored_candidates[:max_auto_skills]]
        selected_ids = {skill.id for skill in selected_skills}

        chunk_skill_ids = list(always_on_ids | selected_ids)
        chunks = self.store.select_relevant_chunks(
            query=query,
            max_chunks=max_chunks,
            max_chars=max_chunk_chars,
            skill_ids=chunk_skill_ids,
        )

        return ResolvedSkillContext(
            always_on_skills=tuple(always_on),
            selected_skills=tuple(selected_skills),
            chunks=tuple(chunks),
        )

    def _score_skill(self, skill: SkillDefinition, query: str) -> float:
        query_tokens = self.store._tokenize(query)  # intentional shared normalization
        if not query_tokens:
            return 0.0

        metadata_tokens = self.store._tokenize(
            "{title} {summary} {tags} {triggers} {body}".format(
                title=skill.title,
                summary=skill.summary,
                tags=" ".join(skill.tags),
                triggers=" ".join(skill.triggers),
                body=skill.body[:800],
            )
        )
        if not metadata_tokens:
            return 0.0

        query_counter = Counter(query_tokens)
        metadata_counter = Counter(metadata_tokens)
        overlap = 0.0
        for token, query_count in query_counter.items():
            overlap += min(query_count, metadata_counter.get(token, 0))

        query_text = query.lower()
        trigger_bonus = 0.0
        for trigger in skill.triggers:
            lowered = trigger.lower()
            if lowered and lowered in query_text:
                trigger_bonus += 3.0

        title_bonus = 1.5 if any(token in skill.title.lower() for token in query_tokens) else 0.0
        tag_bonus = 1.0 if any(token in " ".join(skill.tags).lower() for token in query_tokens) else 0.0
        summary_bonus = 1.0 if query_text and query_text in skill.summary.lower() else 0.0
        priority_bonus = max(skill.priority, 0) / 100.0

        return overlap + trigger_bonus + title_bonus + tag_bonus + summary_bonus + priority_bonus


def describe_resolved_skill_context(context: ResolvedSkillContext) -> str:
    if context.is_empty:
        return "No shared skills were selected for this request."

    parts: List[str] = []
    if context.always_on_skills:
        labels = ", ".join(skill.id for skill in context.always_on_skills)
        parts.append(
            "Loaded {count} always-on skill(s): {labels}.".format(
                count=len(context.always_on_skills),
                labels=labels,
            )
        )
    if context.selected_skills:
        labels = ", ".join(skill.id for skill in context.selected_skills)
        parts.append(
            "Matched {count} request-specific skill(s): {labels}.".format(
                count=len(context.selected_skills),
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
    always_on_ids = {skill.id for skill in context.always_on_skills}
    for skill in context.all_skills:
        items.append(
            {
                "id": skill.id,
                "title": skill.title,
                "type": skill.skill_type,
                "mode": skill.mode,
                "summary": skill.summary,
                "role": "always_on" if skill.id in always_on_ids else "selected",
                "source": skill.source,
            }
        )
    return items
