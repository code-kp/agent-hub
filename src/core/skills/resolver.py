"""
Tests:
- tests/core/skills/test_resolver.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from core.contracts.skills import SkillDefinition, ensure_skill_ids
from core.retrieval.skills import SkillSemanticRetriever
from core.skills.store import SkillChunk, SkillStore


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
        self.semantic = SkillSemanticRetriever(store)

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
        query_vector: Sequence[float] | None = None,
    ) -> ResolvedSkillContext:
        self.store.refresh()
        behavior_skill_ids = set(ensure_skill_ids(behavior_ids))
        behavior_skills = self._resolve_explicit_skills(
            behavior_skill_ids, expected_class="behavior"
        )
        explicit_knowledge_skill_ids = set(ensure_skill_ids(knowledge_ids))

        semantic_context = self._resolve_semantic(
            query=query,
            user_id=user_id,
            behavior_skills=behavior_skills,
            explicit_knowledge_skill_ids=explicit_knowledge_skill_ids,
            max_auto_skills=max_auto_skills,
            max_chunks=max_chunks,
            max_chunk_chars=max_chunk_chars,
            query_vector=query_vector,
        )
        if semantic_context is not None:
            return semantic_context

        return self._resolve_lexical(
            query=query,
            user_id=user_id,
            behavior_skills=behavior_skills,
            explicit_knowledge_skill_ids=explicit_knowledge_skill_ids,
            max_auto_skills=max_auto_skills,
            max_chunks=max_chunks,
            max_chunk_chars=max_chunk_chars,
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

    def _resolve_semantic(
        self,
        *,
        query: str,
        user_id: str,
        behavior_skills: Sequence[SkillDefinition],
        explicit_knowledge_skill_ids: set[str],
        max_auto_skills: int,
        max_chunks: int,
        max_chunk_chars: int,
        query_vector: Sequence[float] | None,
    ) -> ResolvedSkillContext | None:
        if not self.store._tokenize(query):
            return None

        behavior_skill_set = {skill.id for skill in behavior_skills}
        accessible_knowledge = {
            skill.id: skill
            for skill in self.semantic.accessible_knowledge_skills(user_id=user_id)
        }
        searchable_skill_ids = set(accessible_knowledge.keys()) | behavior_skill_set
        if not searchable_skill_ids:
            return None

        def metadata_boost(document, query_tokens: tuple[str, ...]) -> float:
            metadata = document.metadata
            skill_id = str(metadata.get("skill_id") or "").strip()
            boost = 0.0
            if skill_id in explicit_knowledge_skill_ids:
                boost += 0.25
            if skill_id in behavior_skill_set:
                boost += 0.05
            title = str(metadata.get("title") or "").lower()
            heading = str(metadata.get("heading") or "").lower()
            if any(token in title for token in query_tokens):
                boost += 0.05
            if any(token in heading for token in query_tokens):
                boost += 0.05
            return boost

        try:
            matches, _status = self.semantic.search_matches(
                query=query,
                max_results=max(max_chunks * 4, max_auto_skills * 3, 8),
                skill_ids=sorted(searchable_skill_ids),
                metadata_boost=metadata_boost,
                query_vector=query_vector,
            )
        except Exception:
            return None

        if not matches:
            return None

        scored_skills: Dict[str, float] = {}
        for match in matches:
            skill_id = str(match.document.metadata.get("skill_id") or "").strip()
            if not skill_id or skill_id in behavior_skill_set:
                continue
            if skill_id not in accessible_knowledge:
                continue
            previous = scored_skills.get(skill_id)
            if previous is None or match.score > previous:
                scored_skills[skill_id] = match.score

        selected_skill_ids = [
            skill_id
            for skill_id, _score in sorted(
                scored_skills.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]
        selected_skill_ids = self._prune_semantic_skill_ids(
            selected_skill_ids,
            scored_skills=scored_skills,
            explicit_knowledge_skill_ids=explicit_knowledge_skill_ids,
            max_auto_skills=max_auto_skills,
        )
        selected_skills = [
            accessible_knowledge[skill_id]
            for skill_id in selected_skill_ids
            if skill_id in accessible_knowledge
        ]
        chunk_skill_ids = set(selected_skill_ids) | behavior_skill_set
        chunks = self._select_semantic_chunks(
            matches,
            allowed_skill_ids=chunk_skill_ids,
            max_chunks=max_chunks,
            max_chars=max_chunk_chars,
        )
        if len(chunks) < max_chunks and chunk_skill_ids:
            lexical_chunks = self.store.select_relevant_chunks(
                query=query,
                max_chunks=max_chunks,
                max_chars=max_chunk_chars,
                skill_ids=list(chunk_skill_ids),
            )
            chunks = self._merge_chunks(
                chunks,
                lexical_chunks,
                max_chunks=max_chunks,
                max_chars=max_chunk_chars,
            )

        return ResolvedSkillContext(
            behavior=tuple(behavior_skills),
            knowledge=tuple(selected_skills),
            chunks=tuple(chunks),
        )

    def _resolve_lexical(
        self,
        *,
        query: str,
        user_id: str,
        behavior_skills: Sequence[SkillDefinition],
        explicit_knowledge_skill_ids: set[str],
        max_auto_skills: int,
        max_chunks: int,
        max_chunk_chars: int,
    ) -> ResolvedSkillContext:
        behavior_skill_set = {skill.id for skill in behavior_skills}
        knowledge_candidates = self.semantic.accessible_knowledge_skills(user_id=user_id)

        scored_candidates: List[tuple[float, SkillDefinition]] = []
        for skill in knowledge_candidates:
            if skill.id in behavior_skill_set:
                continue
            score = self._score_skill(skill, query)
            if skill.id in explicit_knowledge_skill_ids and score > 0:
                score += 0.75
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

    def _select_semantic_chunks(
        self,
        matches,
        *,
        allowed_skill_ids: set[str],
        max_chunks: int,
        max_chars: int,
    ) -> list[SkillChunk]:
        selected: list[SkillChunk] = []
        selected_ids = set()
        char_count = 0
        for match in matches:
            skill_id = str(match.document.metadata.get("skill_id") or "").strip()
            if allowed_skill_ids and skill_id not in allowed_skill_ids:
                continue
            chunk_id = str(match.document.metadata.get("chunk_id") or "").strip()
            if not chunk_id or chunk_id in selected_ids:
                continue
            chunk = self.store.get_chunk(chunk_id)
            if chunk is None:
                continue
            if selected and char_count + len(chunk.text) > max_chars:
                continue
            selected.append(chunk)
            selected_ids.add(chunk.chunk_id)
            char_count += len(chunk.text)
            if len(selected) >= max_chunks:
                break
        return selected

    def _merge_chunks(
        self,
        primary: Sequence[SkillChunk],
        secondary: Sequence[SkillChunk],
        *,
        max_chunks: int,
        max_chars: int,
    ) -> list[SkillChunk]:
        selected = list(primary)
        selected_ids = {chunk.chunk_id for chunk in selected}
        char_count = sum(len(chunk.text) for chunk in selected)
        for chunk in secondary:
            if chunk.chunk_id in selected_ids:
                continue
            if selected and char_count + len(chunk.text) > max_chars:
                continue
            selected.append(chunk)
            selected_ids.add(chunk.chunk_id)
            char_count += len(chunk.text)
            if len(selected) >= max_chunks:
                break
        return selected

    def _prune_semantic_skill_ids(
        self,
        ordered_skill_ids: Sequence[str],
        *,
        scored_skills: Dict[str, float],
        explicit_knowledge_skill_ids: set[str],
        max_auto_skills: int,
    ) -> list[str]:
        if not ordered_skill_ids:
            return []

        if not explicit_knowledge_skill_ids:
            return list(ordered_skill_ids[:max_auto_skills])

        explicit_scores = [
            score
            for skill_id, score in scored_skills.items()
            if skill_id in explicit_knowledge_skill_ids
        ]
        top_explicit_score = max(explicit_scores) if explicit_scores else 0.0
        selected: list[str] = []
        for skill_id in ordered_skill_ids:
            score = scored_skills.get(skill_id, 0.0)
            if skill_id in explicit_knowledge_skill_ids:
                selected.append(skill_id)
            elif score >= max(top_explicit_score * 0.9, 0.95):
                selected.append(skill_id)
            if len(selected) >= max_auto_skills:
                break
        return selected


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
