from __future__ import annotations

import os
from typing import Optional

from google import genai

from core.retrieval.types import EmbeddingProvider


DEFAULT_GOOGLE_EMBEDDING_MODEL = "text-embedding-004"


class DisabledEmbeddingProvider(EmbeddingProvider):
    def __init__(self, reason: str) -> None:
        self._reason = str(reason or "").strip() or "Embeddings are not configured."

    @property
    def is_available(self) -> bool:
        return False

    @property
    def reason(self) -> str:
        return self._reason

    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        raise RuntimeError(self.reason)


class GoogleEmbeddingProvider(EmbeddingProvider):
    name = "google"

    def __init__(
        self,
        *,
        model_name: str,
        api_key: str,
        batch_size: int = 16,
    ) -> None:
        self.model_name = str(model_name or "").strip() or DEFAULT_GOOGLE_EMBEDDING_MODEL
        self.api_key = str(api_key or "").strip()
        self.batch_size = max(int(batch_size or 1), 1)
        self._client: Optional[genai.Client] = None

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self.model_name)

    @property
    def reason(self) -> str:
        if self.is_available:
            return ""
        return "Google embeddings require GOOGLE_API_KEY or GEMINI_API_KEY."

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        if not self.is_available:
            raise RuntimeError(self.reason)
        normalized_texts = [str(text or "").strip() for text in texts if str(text or "").strip()]
        if not normalized_texts:
            return []

        vectors: list[tuple[float, ...]] = []
        for start in range(0, len(normalized_texts), self.batch_size):
            batch = normalized_texts[start : start + self.batch_size]
            response = self.client.models.embed_content(
                model=self.model_name,
                contents=batch,
            )
            embeddings = list(getattr(response, "embeddings", None) or [])
            if len(embeddings) != len(batch):
                raise RuntimeError("Embedding provider returned an unexpected result count.")
            for item in embeddings:
                values = tuple(float(value) for value in list(getattr(item, "values", None) or []))
                if not values:
                    raise RuntimeError("Embedding provider returned an empty vector.")
                vectors.append(values)
        return vectors


def resolve_embedding_provider() -> EmbeddingProvider:
    provider_name = str(os.getenv("EMBEDDING_PROVIDER") or "").strip().lower()
    if not provider_name:
        return DisabledEmbeddingProvider("Embeddings are disabled because EMBEDDING_PROVIDER is not set.")

    if provider_name == "google":
        api_key = str(
            os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
        ).strip()
        if not api_key:
            return DisabledEmbeddingProvider(
                "Google embeddings are disabled because GOOGLE_API_KEY or GEMINI_API_KEY is not set."
            )
        batch_size = _int_env("EMBEDDING_BATCH_SIZE", default=16)
        return GoogleEmbeddingProvider(
            model_name=str(os.getenv("EMBEDDING_MODEL") or "").strip()
            or DEFAULT_GOOGLE_EMBEDDING_MODEL,
            api_key=api_key,
            batch_size=batch_size,
        )

    return DisabledEmbeddingProvider(
        "Unsupported embedding provider: {provider}.".format(provider=provider_name)
    )


def _int_env(name: str, *, default: int) -> int:
    raw_value = str(os.getenv(name) or "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default
