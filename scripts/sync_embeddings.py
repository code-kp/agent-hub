from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = ROOT / "src"
SKILLS_ROOT = ROOT / "src" / "workspace" / "skills"
CONVERSATIONS_ROOT = ROOT / ".conversations"
EMBEDDINGS_ROOT = ROOT / ".embeddings"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def main(argv: list[str] | None = None) -> int:
    _load_project_env()
    parser = argparse.ArgumentParser(
        description="Build or refresh local semantic retrieval embeddings."
    )
    parser.add_argument(
        "--skills",
        action="store_true",
        help="Sync skill embeddings only.",
    )
    parser.add_argument(
        "--conversations",
        action="store_true",
        help="Sync conversation embeddings only.",
    )
    parser.add_argument(
        "--user",
        default="",
        help="Limit conversation sync to a single user id.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Rebuild the selected index from scratch.",
    )
    args = parser.parse_args(argv)

    selected_skills = bool(args.skills)
    selected_conversations = bool(args.conversations)
    if not selected_skills and not selected_conversations:
        selected_skills = True
        selected_conversations = True

    from core.retrieval.conversations import ConversationSemanticRetriever
    from core.retrieval.index import PreparedIndexSync
    from core.retrieval.skills import SkillSemanticRetriever
    from core.skills.store import SkillStore

    skill_retriever = SkillSemanticRetriever(SkillStore(SKILLS_ROOT))
    conversation_retriever = ConversationSemanticRetriever(
        conversations_root=CONVERSATIONS_ROOT,
        embeddings_root=EMBEDDINGS_ROOT,
    )
    provider = skill_retriever.retriever.provider
    if not provider.is_available:
        print(str(provider.reason or "Embeddings are not configured."), file=sys.stderr)
        return 1

    plans: list[tuple[str, object, PreparedIndexSync]] = []
    if selected_skills:
        documents = skill_retriever._documents()
        plan = skill_retriever.retriever.index.prepare_sync(
            "skills",
            documents,
            provider=provider,
            full_rebuild=args.full,
        )
        plans.append(("skills", skill_retriever, plan))

    if selected_conversations:
        documents = conversation_retriever.builder.build_all_documents(
            user_id=str(args.user or "").strip() or None
        )
        plan = conversation_retriever.retriever.index.prepare_sync(
            "conversations",
            documents,
            provider=provider,
            full_rebuild=args.full,
        )
        plans.append(("conversations", conversation_retriever, plan))

    vectors_by_corpus: dict[str, dict[str, tuple[float, ...]]] = {}
    pending_documents: list[tuple[str, str, str]] = []
    for corpus, _retriever, plan in plans:
        for doc_id in plan.pending_doc_ids:
            pending_documents.append((corpus, doc_id, plan.document_map[doc_id].text))

    if pending_documents:
        vectors = provider.embed_texts([text for _, _, text in pending_documents])
        if len(vectors) != len(pending_documents):
            print("Embedding provider returned an unexpected result count.", file=sys.stderr)
            return 1
        for (corpus, doc_id, _text), vector in zip(pending_documents, vectors):
            vectors_by_corpus.setdefault(corpus, {})[doc_id] = vector

    if selected_skills:
        plan = next(plan for corpus, _retriever, plan in plans if corpus == "skills")
        status = skill_retriever.retriever.index.apply_sync(
            plan,
            provider=provider,
            vectors_by_doc_id=vectors_by_corpus.get("skills"),
        )
        print(
            "skills: indexed={indexed}/{total} missing={missing} stale={stale} extra={extra}".format(
                indexed=status.indexed_documents,
                total=status.total_documents,
                missing=status.missing_count,
                stale=status.stale_count,
                extra=status.extra_count,
            )
        )

    if selected_conversations:
        plan = next(
            plan for corpus, _retriever, plan in plans if corpus == "conversations"
        )
        status = conversation_retriever.retriever.index.apply_sync(
            plan,
            provider=provider,
            vectors_by_doc_id=vectors_by_corpus.get("conversations"),
        )
        print(
            "conversations: indexed={indexed}/{total} missing={missing} stale={stale} extra={extra}".format(
                indexed=status.indexed_documents,
                total=status.total_documents,
                missing=status.missing_count,
                stale=status.stale_count,
                extra=status.extra_count,
            )
        )

    return 0

def _load_project_env() -> None:
    env_path = _resolve_env_path()
    if not env_path.is_file():
        return

    for key, value in dotenv_values(env_path).items():
        if not key or value is None:
            continue
        if os.environ.get(key):
            continue
        os.environ[key] = value


def _resolve_env_path() -> Path:
    for directory in ROOT.parents:
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return ROOT / ".env"


if __name__ == "__main__":
    raise SystemExit(main())
