from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Sequence

from core.retrieval.types import DirtyIndexStatus, EmbeddingProvider, RetrievalDocument


INDEX_VERSION = 1


@dataclass(frozen=True)
class StoredEmbeddingRecord:
    corpus: str
    doc_id: str
    source_id: str
    fingerprint: str
    text: str
    metadata: dict[str, object]
    provider_name: str
    model_name: str
    vector: tuple[float, ...]
    updated_at: str

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> "StoredEmbeddingRecord | None":
        doc_id = str(payload.get("doc_id") or "").strip()
        corpus = str(payload.get("corpus") or "").strip()
        if not doc_id or not corpus:
            return None
        vector = tuple(float(value) for value in list(payload.get("vector") or []))
        if not vector:
            return None
        metadata = payload.get("metadata")
        return cls(
            corpus=corpus,
            doc_id=doc_id,
            source_id=str(payload.get("source_id") or "").strip(),
            fingerprint=str(payload.get("fingerprint") or "").strip(),
            text=str(payload.get("text") or ""),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
            provider_name=str(payload.get("provider_name") or "").strip(),
            model_name=str(payload.get("model_name") or "").strip(),
            vector=vector,
            updated_at=str(payload.get("updated_at") or "").strip(),
        )

    @classmethod
    def from_document(
        cls,
        *,
        corpus: str,
        document: RetrievalDocument,
        provider: EmbeddingProvider,
        vector: Iterable[float],
    ) -> "StoredEmbeddingRecord":
        return cls(
            corpus=corpus,
            doc_id=document.doc_id,
            source_id=document.source_id,
            fingerprint=document.fingerprint,
            text=document.text,
            metadata=dict(document.metadata),
            provider_name=str(provider.name or "").strip(),
            model_name=str(provider.model_name or "").strip(),
            vector=tuple(float(value) for value in vector),
            updated_at=_utc_now(),
        )

    def to_json(self) -> dict[str, object]:
        return {
            "corpus": self.corpus,
            "doc_id": self.doc_id,
            "source_id": self.source_id,
            "fingerprint": self.fingerprint,
            "text": self.text,
            "metadata": self.metadata,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "vector": list(self.vector),
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class PreparedIndexSync:
    corpus: str
    document_map: dict[str, RetrievalDocument]
    records: dict[str, StoredEmbeddingRecord]
    status: DirtyIndexStatus
    pending_doc_ids: tuple[str, ...]
    extra_doc_ids: tuple[str, ...]
    full_rebuild: bool = False


class LocalEmbeddingIndex:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def mark_dirty(self, corpus: str, *, key: str = "default") -> None:
        marker_dir = self.root / "dirty" / str(corpus or "default").strip()
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker_path = marker_dir / "{key}.json".format(key=_safe_marker_name(key))
        marker_path.write_text(
            json.dumps({"corpus": corpus, "key": key, "updated_at": _utc_now()}),
            encoding="utf-8",
        )

    def clear_dirty(self, corpus: str) -> None:
        marker_dir = self.root / "dirty" / str(corpus or "default").strip()
        if not marker_dir.exists():
            return
        for path in marker_dir.glob("*.json"):
            path.unlink(missing_ok=True)
        marker_dir.rmdir()

    def load_records(self, corpus: str) -> Dict[str, StoredEmbeddingRecord]:
        path = self._records_path(corpus)
        if not path.exists():
            return {}

        records: Dict[str, StoredEmbeddingRecord] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            record = StoredEmbeddingRecord.from_json(payload)
            if record is None:
                continue
            records[record.doc_id] = record
        return records

    def inspect(
        self,
        corpus: str,
        documents: Iterable[RetrievalDocument],
        *,
        provider: EmbeddingProvider | None = None,
    ) -> DirtyIndexStatus:
        document_map = {document.doc_id: document for document in documents}
        records = self.load_records(corpus)
        provider_available = bool(provider and provider.is_available)

        missing: list[str] = []
        stale: list[str] = []
        indexed_documents = 0
        for doc_id, document in document_map.items():
            record = records.get(doc_id)
            if record is None:
                missing.append(doc_id)
                continue
            provider_mismatch = bool(
                provider_available
                and (
                    record.provider_name != str(provider.name or "").strip()
                    or record.model_name != str(provider.model_name or "").strip()
                )
            )
            if provider_mismatch or record.fingerprint != document.fingerprint:
                stale.append(doc_id)
                continue
            indexed_documents += 1

        extra = sorted(doc_id for doc_id in records.keys() if doc_id not in document_map)
        return DirtyIndexStatus(
            corpus=corpus,
            total_documents=len(document_map),
            indexed_documents=indexed_documents,
            missing_doc_ids=tuple(sorted(missing)),
            stale_doc_ids=tuple(sorted(stale)),
            extra_doc_ids=tuple(extra),
            provider_available=provider_available,
            reason="" if provider is None else str(getattr(provider, "reason", "") or ""),
        )

    def sync(
        self,
        corpus: str,
        documents: Iterable[RetrievalDocument],
        *,
        provider: EmbeddingProvider,
        full_rebuild: bool = False,
        max_documents: int | None = None,
    ) -> DirtyIndexStatus:
        if not provider.is_available:
            document_map = {document.doc_id: document for document in documents}
            return self.inspect(corpus, document_map.values(), provider=provider)

        plan = self.prepare_sync(
            corpus,
            documents,
            provider=provider,
            full_rebuild=full_rebuild,
            max_documents=max_documents,
        )
        if not plan.pending_doc_ids:
            return self.apply_sync(plan, provider=provider)

        vectors = provider.embed_texts(
            [plan.document_map[doc_id].text for doc_id in plan.pending_doc_ids]
        )
        if len(vectors) != len(plan.pending_doc_ids):
            raise RuntimeError("Embedding sync returned an unexpected number of vectors.")
        return self.apply_sync(
            plan,
            provider=provider,
            vectors_by_doc_id={
                doc_id: vector for doc_id, vector in zip(plan.pending_doc_ids, vectors)
            },
        )

    def prepare_sync(
        self,
        corpus: str,
        documents: Iterable[RetrievalDocument],
        *,
        provider: EmbeddingProvider,
        full_rebuild: bool = False,
        max_documents: int | None = None,
    ) -> PreparedIndexSync:
        document_map = {document.doc_id: document for document in documents}
        records = {} if full_rebuild else self.load_records(corpus)
        status = self.inspect(corpus, document_map.values(), provider=provider)
        pending_doc_ids = list(status.missing_doc_ids + status.stale_doc_ids)
        if max_documents is not None:
            pending_doc_ids = pending_doc_ids[: max(int(max_documents), 0)]
        return PreparedIndexSync(
            corpus=corpus,
            document_map=document_map,
            records=records,
            status=status,
            pending_doc_ids=tuple(pending_doc_ids),
            extra_doc_ids=tuple(status.extra_doc_ids),
            full_rebuild=full_rebuild,
        )

    def apply_sync(
        self,
        plan: PreparedIndexSync,
        *,
        provider: EmbeddingProvider,
        vectors_by_doc_id: Dict[str, Sequence[float]] | None = None,
    ) -> DirtyIndexStatus:
        if not provider.is_available:
            return self.inspect(
                plan.corpus,
                plan.document_map.values(),
                provider=provider,
            )

        pending_doc_ids = list(plan.pending_doc_ids)
        extra_doc_ids = set(plan.extra_doc_ids)
        if (
            not plan.full_rebuild
            and not pending_doc_ids
            and not extra_doc_ids
        ):
            self.clear_dirty(plan.corpus)
            return plan.status

        records = dict(plan.records)
        if pending_doc_ids:
            if vectors_by_doc_id is None:
                raise RuntimeError("Missing vectors for pending embedding sync.")
            for doc_id in pending_doc_ids:
                vector = vectors_by_doc_id.get(doc_id)
                if vector is None:
                    raise RuntimeError(
                        "Embedding sync is missing a vector for document: {doc_id}.".format(
                            doc_id=doc_id
                        )
                    )
                records[doc_id] = StoredEmbeddingRecord.from_document(
                    corpus=plan.corpus,
                    document=plan.document_map[doc_id],
                    provider=provider,
                    vector=vector,
                )

        if extra_doc_ids:
            records = {
                doc_id: record
                for doc_id, record in records.items()
                if doc_id not in extra_doc_ids
            }

        self._write_records(plan.corpus, records)
        post_status = self.inspect(
            plan.corpus,
            plan.document_map.values(),
            provider=provider,
        )
        self._write_manifest(
            plan.corpus,
            provider=provider,
            document_count=len(records),
            indexed_documents=post_status.indexed_documents,
        )
        if not post_status.has_changes:
            self.clear_dirty(plan.corpus)
        return post_status

    def _records_path(self, corpus: str) -> Path:
        return self.root / "{corpus}.jsonl".format(corpus=str(corpus or "default"))

    def _manifest_path(self) -> Path:
        return self.root / "manifest.json"

    def _write_records(
        self,
        corpus: str,
        records: Dict[str, StoredEmbeddingRecord],
    ) -> None:
        path = self._records_path(corpus)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix("{suffix}.tmp".format(suffix=path.suffix))
        lines = [
            json.dumps(
                record.to_json(),
                ensure_ascii=True,
                separators=(",", ":"),
            )
            for _, record in sorted(records.items(), key=lambda item: item[0])
        ]
        temp_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        temp_path.replace(path)

    def _write_manifest(
        self,
        corpus: str,
        *,
        provider: EmbeddingProvider,
        document_count: int,
        indexed_documents: int,
    ) -> None:
        path = self._manifest_path()
        payload: dict[str, object]
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                loaded = {}
            payload = dict(loaded) if isinstance(loaded, dict) else {}
        else:
            payload = {}

        corpora = payload.get("corpora")
        if not isinstance(corpora, dict):
            corpora = {}

        corpora[corpus] = {
            "provider": str(provider.name or "").strip(),
            "model": str(provider.model_name or "").strip(),
            "document_count": int(document_count),
            "indexed_documents": int(indexed_documents),
            "updated_at": _utc_now(),
        }
        payload["version"] = INDEX_VERSION
        payload["corpora"] = corpora

        temp_path = path.with_suffix("{suffix}.tmp".format(suffix=path.suffix))
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp_path.replace(path)


def _safe_marker_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "default"
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in text)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
