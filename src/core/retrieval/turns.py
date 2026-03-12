from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from core.retrieval.conversations import ConversationSemanticRetriever
from core.retrieval.types import RetrievalMatch
from core.skills.resolver import ResolvedSkillContext


@dataclass(frozen=True)
class TurnContextBundle:
    skills: ResolvedSkillContext = field(default_factory=ResolvedSkillContext)
    recalled_conversations: tuple[RetrievalMatch, ...] = ()

    @property
    def is_empty(self) -> bool:
        return self.skills.is_empty and not self.recalled_conversations


class TurnContextResolver:
    def __init__(self, conversation_retriever: ConversationSemanticRetriever) -> None:
        self.conversation_retriever = conversation_retriever

    def resolve(
        self,
        *,
        query: str,
        user_id: str,
        conversation_id: str | None,
        agent_id: str,
        history: Sequence[dict[str, str]] | None,
        skill_context: ResolvedSkillContext,
        max_conversation_matches: int = 3,
        query_vector: Sequence[float] | None = None,
    ) -> TurnContextBundle:
        matches, _status = self.conversation_retriever.recall(
            query=query,
            user_id=user_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            history=history,
            max_results=max_conversation_matches,
            query_vector=query_vector,
        )
        return TurnContextBundle(
            skills=skill_context,
            recalled_conversations=tuple(matches),
        )


def describe_turn_context(bundle: TurnContextBundle) -> str:
    parts: list[str] = []
    if not bundle.skills.is_empty:
        parts.append("Skill guidance is ready for this turn.")
    if bundle.recalled_conversations:
        parts.append(
            "Retrieved {count} related conversation excerpt(s).".format(
                count=len(bundle.recalled_conversations)
            )
        )
    if not parts:
        return "No extra semantic context was selected for this turn."
    return " ".join(parts)


def serialize_recalled_conversations(
    bundle: TurnContextBundle,
) -> list[dict[str, object]]:
    return [
        {
            "conversation_id": str(match.document.metadata.get("conversation_id") or ""),
            "title": str(match.document.metadata.get("title") or ""),
            "agent_id": str(match.document.metadata.get("agent_id") or ""),
            "window_start": int(match.document.metadata.get("window_start") or 0),
            "window_end": int(match.document.metadata.get("window_end") or 0),
            "score": round(match.score, 4),
            "text": match.document.text,
        }
        for match in bundle.recalled_conversations
    ]
