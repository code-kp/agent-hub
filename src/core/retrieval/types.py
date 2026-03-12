from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievalDocument:
    corpus: str
    doc_id: str
    source_id: str
    text: str
    fingerprint: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalMatch:
    document: RetrievalDocument
    score: float
    vector_score: float
    lexical_score: float
    metadata_boost: float = 0.0


@dataclass(frozen=True)
class DirtyIndexStatus:
    corpus: str
    total_documents: int
    indexed_documents: int
    missing_doc_ids: tuple[str, ...] = ()
    stale_doc_ids: tuple[str, ...] = ()
    extra_doc_ids: tuple[str, ...] = ()
    provider_available: bool = False
    reason: str = ""

    @property
    def missing_count(self) -> int:
        return len(self.missing_doc_ids)

    @property
    def stale_count(self) -> int:
        return len(self.stale_doc_ids)

    @property
    def extra_count(self) -> int:
        return len(self.extra_doc_ids)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.missing_doc_ids or self.stale_doc_ids or self.extra_doc_ids
        )

    @property
    def is_ready(self) -> bool:
        return not self.has_changes


class EmbeddingProvider(ABC):
    name: str = ""
    model_name: str = ""

    @property
    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @property
    def reason(self) -> str:
        return ""

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        raise NotImplementedError
