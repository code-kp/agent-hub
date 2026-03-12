from __future__ import annotations

import os
from typing import Callable, Iterable, Sequence

from core.retrieval.index import LocalEmbeddingIndex
from core.retrieval.providers import resolve_embedding_provider
from core.retrieval.scoring import (
    cosine_similarity,
    lexical_overlap_score,
    tokenize,
)
from core.retrieval.types import DirtyIndexStatus, RetrievalDocument, RetrievalMatch


MetadataBoost = Callable[[RetrievalDocument, tuple[str, ...]], float]
DocumentFilter = Callable[[RetrievalDocument], bool]


class SemanticRetriever:
    def __init__(self, index: LocalEmbeddingIndex) -> None:
        self.index = index
        self.provider = resolve_embedding_provider()
        self.lazy_sync_limit = _int_env("EMBEDDING_LAZY_MAX_DOCUMENTS", default=12)

    def dirty_status(
        self,
        corpus: str,
        documents: Iterable[RetrievalDocument],
    ) -> DirtyIndexStatus:
        return self.index.inspect(corpus, documents, provider=self.provider)

    def sync_documents(
        self,
        corpus: str,
        documents: Iterable[RetrievalDocument],
        *,
        full_rebuild: bool = False,
        max_documents: int | None = None,
    ) -> DirtyIndexStatus:
        return self.index.sync(
            corpus,
            documents,
            provider=self.provider,
            full_rebuild=full_rebuild,
            max_documents=max_documents,
        )

    def embed_query(self, query: str) -> tuple[float, ...] | None:
        if not self.provider.is_available:
            raise RuntimeError(self.provider.reason)
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return None
        query_vector_list = self.provider.embed_texts([normalized_query])
        if not query_vector_list:
            return None
        return query_vector_list[0]

    def search(
        self,
        corpus: str,
        documents: Iterable[RetrievalDocument],
        *,
        query: str,
        max_results: int,
        metadata_boost: MetadataBoost | None = None,
        document_filter: DocumentFilter | None = None,
        lazy_sync: bool = True,
        max_sync_documents: int | None = None,
        query_vector: Sequence[float] | None = None,
    ) -> tuple[list[RetrievalMatch], DirtyIndexStatus]:
        if not self.provider.is_available:
            raise RuntimeError(self.provider.reason)

        query_tokens = tokenize(query)
        if not query_tokens:
            return [], self.index.inspect(corpus, documents, provider=self.provider)

        document_list = list(documents)
        if not document_list:
            return [], self.index.inspect(corpus, document_list, provider=self.provider)

        status = self.index.inspect(corpus, document_list, provider=self.provider)
        if lazy_sync and status.has_changes:
            status = self.index.sync(
                corpus,
                document_list,
                provider=self.provider,
                max_documents=max_sync_documents or self.lazy_sync_limit,
            )

        resolved_query_vector = tuple(float(value) for value in list(query_vector or []))
        if not resolved_query_vector:
            embedded_query = self.embed_query(query)
            if embedded_query is None:
                return [], status
            resolved_query_vector = embedded_query

        records = self.index.load_records(corpus)
        matches: list[RetrievalMatch] = []
        for document in document_list:
            if document_filter is not None and not document_filter(document):
                continue

            record = records.get(document.doc_id)
            if record is None:
                continue
            if record.fingerprint != document.fingerprint:
                continue
            if (
                record.provider_name != str(self.provider.name or "").strip()
                or record.model_name != str(self.provider.model_name or "").strip()
            ):
                continue

            vector_score = cosine_similarity(resolved_query_vector, record.vector)
            lexical_score = lexical_overlap_score(query_tokens, tokenize(document.text))
            boost = metadata_boost(document, query_tokens) if metadata_boost else 0.0
            score = vector_score + (0.25 * lexical_score) + boost
            if score <= 0:
                continue
            matches.append(
                RetrievalMatch(
                    document=document,
                    score=score,
                    vector_score=vector_score,
                    lexical_score=lexical_score,
                    metadata_boost=boost,
                )
            )

        matches.sort(
            key=lambda item: (
                item.score,
                item.vector_score,
                item.lexical_score,
                item.document.doc_id,
            ),
            reverse=True,
        )
        return matches[:max_results], status


def _int_env(name: str, *, default: int) -> int:
    raw_value = str(os.getenv(name) or "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default
