from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from core.contracts.skills import SkillDefinition
from core.skills.parser import parse_skill_file


TOKEN_RE = re.compile(r"[a-z0-9]{2,}", re.IGNORECASE)


@dataclass(frozen=True)
class SkillChunk:
    chunk_id: str
    skill_id: str
    source: str
    heading: str
    text: str
    tokens: tuple[str, ...]

    @property
    def label(self) -> str:
        return "{skill_id} :: {heading}".format(skill_id=self.skill_id, heading=self.heading)


class SkillStore:
    def __init__(self, skills_dir: Path, max_chunk_chars: int = 900) -> None:
        self.skills_dir = skills_dir
        self.max_chunk_chars = max_chunk_chars
        self._skills: Dict[str, SkillDefinition] = {}
        self._chunks: List[SkillChunk] = []
        self._doc_frequency: Counter[str] = Counter()
        self._index_signature: tuple[tuple[str, int], ...] = ()

    def refresh(self) -> None:
        if not self.skills_dir.exists():
            self._skills = {}
            self._chunks = []
            self._doc_frequency = Counter()
            self._index_signature = ()
            return

        files = sorted(self.skills_dir.rglob("*.md"))
        signature = tuple(
            (str(path.relative_to(self.skills_dir)), int(path.stat().st_mtime_ns))
            for path in files
        )
        if signature == self._index_signature:
            return

        skills: Dict[str, SkillDefinition] = {}
        chunks: List[SkillChunk] = []
        for path in files:
            definition = parse_skill_file(path, self.skills_dir)
            if definition.id in skills:
                raise ValueError("Duplicate skill id discovered: {skill_id}".format(skill_id=definition.id))
            skills[definition.id] = definition
            chunks.extend(self._chunk_skill(definition))

        self._skills = skills
        self._chunks = chunks
        self._doc_frequency = Counter()
        for chunk in chunks:
            for token in set(chunk.tokens):
                self._doc_frequency[token] += 1
        self._index_signature = signature

    def list_skills(self) -> List[SkillDefinition]:
        self.refresh()
        return [self._skills[key] for key in sorted(self._skills.keys())]

    def get_skill(self, skill_id: str) -> Optional[SkillDefinition]:
        self.refresh()
        return self._skills.get(skill_id.strip())

    def get_skill_by_source(self, source: str) -> Optional[SkillDefinition]:
        self.refresh()
        normalized = str(source or "").strip().replace("\\", "/")
        for skill in self._skills.values():
            if skill.source == normalized:
                return skill
        return None

    def describe(self) -> List[Dict[str, object]]:
        self.refresh()
        return [
            {
                "id": skill.id,
                "title": skill.title,
                "type": skill.skill_type,
                "mode": skill.mode,
                "summary": skill.summary,
                "source": skill.source,
            }
            for skill in self.list_skills()
        ]

    def select_relevant_chunks(
        self,
        query: str,
        max_chunks: int = 4,
        max_chars: int = 2200,
        skill_ids: Optional[Sequence[str]] = None,
    ) -> List[SkillChunk]:
        self.refresh()
        query_tokens = self._tokenize(query)
        selected_ids = {value.strip() for value in list(skill_ids or []) if str(value or "").strip()}
        chunk_pool = [
            chunk
            for chunk in self._chunks
            if not selected_ids or chunk.skill_id in selected_ids
        ]

        if not query_tokens:
            return self._take_first_chunks(chunk_pool, max_chunks=max_chunks, max_chars=max_chars)

        scored: List[tuple[float, SkillChunk]] = []
        query_counter = Counter(query_tokens)
        query_text = query.lower()
        corpus_size = max(len(chunk_pool), 1)

        for chunk in chunk_pool:
            chunk_counter = Counter(chunk.tokens)
            overlap_score = 0.0
            for token, query_count in query_counter.items():
                if token not in chunk_counter:
                    continue
                doc_freq = self._doc_frequency.get(token, 1)
                idf = math.log((1 + corpus_size) / (1 + doc_freq)) + 1
                overlap_score += min(query_count, chunk_counter[token]) * idf

            heading_bonus = 1.5 if any(token in chunk.heading.lower() for token in query_tokens) else 0.0
            file_bonus = 1.0 if any(token in chunk.source.lower() for token in query_tokens) else 0.0
            phrase_bonus = 2.0 if query_text in chunk.text.lower() else 0.0
            score = overlap_score + heading_bonus + file_bonus + phrase_bonus
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return self._take_scored_chunks(scored, max_chunks=max_chunks, max_chars=max_chars)

    def search(
        self,
        query: str,
        max_results: int = 3,
        skill_ids: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, str]]:
        chunks = self.select_relevant_chunks(
            query=query,
            max_chunks=max_results,
            max_chars=3000,
            skill_ids=skill_ids,
        )
        return [
            {
                "chunk_id": chunk.chunk_id,
                "skill_id": chunk.skill_id,
                "source": chunk.source,
                "heading": chunk.heading,
                "text": chunk.text,
            }
            for chunk in chunks
        ]

    def _chunk_skill(self, definition: SkillDefinition) -> List[SkillChunk]:
        lines = definition.body.splitlines()
        heading_stack: List[str] = []
        buffer: List[str] = []
        chunks: List[SkillChunk] = []
        chunk_index = 0

        def flush() -> None:
            nonlocal chunk_index
            text = "\n".join(buffer).strip()
            buffer.clear()
            if not text:
                return
            heading = " > ".join(heading_stack) if heading_stack else "Overview"
            for piece in self._split_large_block(text):
                tokens = tuple(
                    self._tokenize(
                        "{source} {title} {summary} {heading} {piece}".format(
                            source=definition.source,
                            title=definition.title,
                            summary=definition.summary,
                            heading=heading,
                            piece=piece,
                        )
                    )
                )
                chunk_index += 1
                chunks.append(
                    SkillChunk(
                        chunk_id="{skill_id}:{idx}".format(skill_id=definition.id, idx=chunk_index),
                        skill_id=definition.id,
                        source=definition.source,
                        heading=heading,
                        text=piece,
                        tokens=tokens,
                    )
                )

        for raw_line in lines:
            line = raw_line.rstrip()
            if line.startswith("#"):
                flush()
                level = len(line) - len(line.lstrip("#"))
                title = line[level:].strip() or "Untitled"
                heading_stack[:] = heading_stack[: max(level - 1, 0)]
                heading_stack.append(title)
                continue

            if not line.strip():
                flush()
                continue

            buffer.append(line)

        flush()
        return chunks

    def _take_first_chunks(
        self,
        chunks: Sequence[SkillChunk],
        *,
        max_chunks: int,
        max_chars: int,
    ) -> List[SkillChunk]:
        selected: List[SkillChunk] = []
        total_chars = 0
        seen_ids = set()
        for chunk in chunks:
            if chunk.chunk_id in seen_ids:
                continue
            projected = total_chars + len(chunk.text)
            if selected and projected > max_chars:
                continue
            selected.append(chunk)
            seen_ids.add(chunk.chunk_id)
            total_chars = projected
            if len(selected) >= max_chunks:
                break
        return selected

    def _take_scored_chunks(
        self,
        scored: Sequence[tuple[float, SkillChunk]],
        *,
        max_chunks: int,
        max_chars: int,
    ) -> List[SkillChunk]:
        selected: List[SkillChunk] = []
        total_chars = 0
        seen_ids = set()

        for _, chunk in scored:
            if chunk.chunk_id in seen_ids:
                continue
            projected = total_chars + len(chunk.text)
            if selected and projected > max_chars:
                continue
            selected.append(chunk)
            seen_ids.add(chunk.chunk_id)
            total_chars = projected
            if len(selected) >= max_chunks:
                break

        return selected

    def _split_large_block(self, text: str) -> Iterable[str]:
        if len(text) <= self.max_chunk_chars:
            return [text]

        sentences = re.split(r"(?<=[.!?])\s+", text)
        parts: List[str] = []
        current = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            candidate = "{current} {sentence}".format(current=current, sentence=sentence).strip()
            if current and len(candidate) > self.max_chunk_chars:
                parts.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            parts.append(current)
        return parts or [text[: self.max_chunk_chars]]

    def _tokenize(self, text: str) -> List[str]:
        return [self._normalize_token(token) for token in TOKEN_RE.findall(text)]

    def _normalize_token(self, token: str) -> str:
        normalized = token.lower()
        if len(normalized) > 4 and normalized.endswith("ies"):
            return normalized[:-3] + "y"
        if len(normalized) > 4 and normalized.endswith("s"):
            return normalized[:-1]
        return normalized
