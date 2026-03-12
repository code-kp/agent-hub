from __future__ import annotations

from pathlib import Path
from typing import Sequence

from core.contracts.skills import SkillDefinition
from core.retrieval.index import LocalEmbeddingIndex
from core.retrieval.scoring import stable_fingerprint
from core.retrieval.service import SemanticRetriever
from core.retrieval.types import DirtyIndexStatus, RetrievalDocument, RetrievalMatch
from core.skills.store import SkillChunk, SkillStore
from core.skills.uploads import build_user_upload_scope


class SkillSemanticRetriever:
    def __init__(self, store: SkillStore) -> None:
        self.store = store
        self.retriever = SemanticRetriever(LocalEmbeddingIndex(self._embeddings_root()))

    def dirty_status(self, *, skill_ids: Sequence[str] | None = None) -> DirtyIndexStatus:
        documents = self._documents(skill_ids=skill_ids)
        return self.retriever.dirty_status("skills", documents)

    def sync(
        self,
        *,
        skill_ids: Sequence[str] | None = None,
        full_rebuild: bool = False,
    ) -> DirtyIndexStatus:
        documents = self._documents(skill_ids=skill_ids)
        return self.retriever.sync_documents(
            "skills",
            documents,
            full_rebuild=full_rebuild,
        )

    def search_matches(
        self,
        *,
        query: str,
        max_results: int,
        skill_ids: Sequence[str] | None = None,
        metadata_boost=None,
        query_vector: Sequence[float] | None = None,
    ) -> tuple[list[RetrievalMatch], DirtyIndexStatus]:
        documents = self._documents(skill_ids=skill_ids)
        return self.retriever.search(
            "skills",
            documents,
            query=query,
            max_results=max_results,
            metadata_boost=metadata_boost,
            query_vector=query_vector,
        )

    def search(
        self,
        *,
        query: str,
        max_results: int = 3,
        skill_ids: Sequence[str] | None = None,
        query_vector: Sequence[float] | None = None,
    ) -> list[dict[str, str]]:
        try:
            matches, _status = self.search_matches(
                query=query,
                max_results=max_results,
                skill_ids=skill_ids,
                query_vector=query_vector,
            )
        except Exception:
            return self.store.search(
                query=query,
                max_results=max_results,
                skill_ids=skill_ids,
            )

        if not matches:
            return self.store.search(
                query=query,
                max_results=max_results,
                skill_ids=skill_ids,
            )
        return [
            {
                "chunk_id": str(match.document.metadata.get("chunk_id") or match.document.doc_id),
                "skill_id": str(match.document.metadata.get("skill_id") or ""),
                "source": str(match.document.metadata.get("source") or ""),
                "heading": str(match.document.metadata.get("heading") or ""),
                "text": str(match.document.metadata.get("chunk_text") or match.document.text),
            }
            for match in matches
        ]

    def accessible_knowledge_skills(self, *, user_id: str) -> list[SkillDefinition]:
        self.store.refresh()
        upload_scope = build_user_upload_scope(user_id)
        resolved: list[SkillDefinition] = []
        for skill in self.store.list_skills():
            if skill.skill_class != "knowledge":
                continue
            if skill.id.startswith("uploads.") and skill.id != upload_scope and not skill.id.startswith(upload_scope + "."):
                continue
            resolved.append(skill)
        return resolved

    def _documents(
        self,
        *,
        skill_ids: Sequence[str] | None = None,
    ) -> list[RetrievalDocument]:
        self.store.refresh()
        selected_skill_ids = {
            str(skill_id or "").strip()
            for skill_id in list(skill_ids or [])
            if str(skill_id or "").strip()
        }
        documents: list[RetrievalDocument] = []
        for chunk in self.store.list_chunks():
            if selected_skill_ids and chunk.skill_id not in selected_skill_ids:
                continue
            skill = self.store.get_skill(chunk.skill_id)
            if skill is None:
                continue
            documents.append(self._chunk_document(skill=skill, chunk=chunk))
        return documents

    def _chunk_document(
        self,
        *,
        skill: SkillDefinition,
        chunk: SkillChunk,
    ) -> RetrievalDocument:
        text = "\n".join(
            part
            for part in [
                "Skill: {skill_id}".format(skill_id=skill.id),
                "Title: {title}".format(title=skill.title),
                "Summary: {summary}".format(summary=skill.summary),
                "Section: {heading}".format(heading=chunk.heading),
                chunk.text,
            ]
            if part
        )
        return RetrievalDocument(
            corpus="skills",
            doc_id=chunk.chunk_id,
            source_id=skill.source,
            text=text,
            fingerprint=stable_fingerprint(
                skill.id,
                skill.source,
                skill.title,
                skill.summary,
                chunk.chunk_id,
                chunk.heading,
                chunk.text,
            ),
            metadata={
                "skill_id": skill.id,
                "class": skill.skill_class,
                "source": skill.source,
                "title": skill.title,
                "summary": skill.summary,
                "heading": chunk.heading,
                "chunk_id": chunk.chunk_id,
                "chunk_text": chunk.text,
            },
        )

    def _embeddings_root(self) -> Path:
        parts = list(self.store.skills_dir.parts)
        if len(parts) >= 3 and tuple(parts[-3:]) == ("src", "workspace", "skills"):
            return self.store.skills_dir.parent.parent.parent / ".embeddings"
        return self.store.skills_dir / ".embeddings"
