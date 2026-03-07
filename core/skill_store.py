from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List


TOKEN_RE = re.compile(r"[a-z0-9]{2,}", re.IGNORECASE)


@dataclass
class SkillChunk:
    chunk_id: str
    source: str
    heading: str
    text: str
    tokens: tuple[str, ...]

    @property
    def label(self) -> str:
        return "{source} :: {heading}".format(source=self.source, heading=self.heading)


class SkillStore:
    def __init__(self, skills_dir: Path, max_chunk_chars: int = 900) -> None:
        self.skills_dir = skills_dir
        self.max_chunk_chars = max_chunk_chars
        self._chunks: List[SkillChunk] = []
        self._doc_frequency: Counter[str] = Counter()
        self._index_signature: tuple[tuple[str, int], ...] = ()

    def refresh(self) -> None:
        if not self.skills_dir.exists():
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

        chunks: List[SkillChunk] = []
        for path in files:
            relative_path = str(path.relative_to(self.skills_dir))
            content = path.read_text(encoding="utf-8")
            chunks.extend(self._chunk_markdown(relative_path, content))

        self._chunks = chunks
        self._doc_frequency = Counter()
        for chunk in chunks:
            for token in set(chunk.tokens):
                self._doc_frequency[token] += 1
        self._index_signature = signature

    def describe(self) -> List[Dict[str, object]]:
        self.refresh()
        grouped: Dict[str, int] = {}
        for chunk in self._chunks:
            grouped.setdefault(chunk.source, 0)
            grouped[chunk.source] += 1
        return [
            {"file": file_name, "chunks": count}
            for file_name, count in sorted(grouped.items())
        ]

    def select_relevant_chunks(
        self,
        query: str,
        max_chunks: int = 4,
        max_chars: int = 2200,
    ) -> List[SkillChunk]:
        self.refresh()
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return self._chunks[:max_chunks]

        scored: List[tuple[float, SkillChunk]] = []
        query_counter = Counter(query_tokens)
        query_text = query.lower()
        corpus_size = max(len(self._chunks), 1)

        for chunk in self._chunks:
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

    def search(self, query: str, max_results: int = 3) -> List[Dict[str, str]]:
        chunks = self.select_relevant_chunks(query=query, max_chunks=max_results, max_chars=3000)
        return [
            {
                "chunk_id": chunk.chunk_id,
                "source": chunk.source,
                "heading": chunk.heading,
                "text": chunk.text,
            }
            for chunk in chunks
        ]

    def _chunk_markdown(self, source: str, content: str) -> List[SkillChunk]:
        lines = content.splitlines()
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
                        "{source} {heading} {piece}".format(
                            source=source,
                            heading=heading,
                            piece=piece,
                        )
                    )
                )
                chunk_index += 1
                chunks.append(
                    SkillChunk(
                        chunk_id="{source}:{idx}".format(source=source, idx=chunk_index),
                        source=source,
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

