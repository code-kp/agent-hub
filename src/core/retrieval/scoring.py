from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Iterable, Sequence


TOKEN_RE = re.compile(r"[a-z0-9]{2,}", re.IGNORECASE)


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(match.group(0).lower() for match in TOKEN_RE.finditer(text or ""))


def stable_fingerprint(*parts: str) -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    for part in parts:
        digest.update(str(part or "").encode("utf-8"))
        digest.update(b"\x1f")
    return digest.hexdigest()


def cosine_similarity(
    left: Sequence[float] | Iterable[float],
    right: Sequence[float] | Iterable[float],
) -> float:
    left_values = tuple(float(value) for value in left)
    right_values = tuple(float(value) for value in right)
    if not left_values or not right_values or len(left_values) != len(right_values):
        return 0.0

    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for left_value, right_value in zip(left_values, right_values):
        dot += left_value * right_value
        left_norm += left_value * left_value
        right_norm += right_value * right_value

    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))


def lexical_overlap_score(
    query_tokens: Sequence[str],
    document_tokens: Sequence[str],
) -> float:
    if not query_tokens or not document_tokens:
        return 0.0
    query_counter = Counter(query_tokens)
    document_counter = Counter(document_tokens)
    matched = 0.0
    for token, query_count in query_counter.items():
        matched += min(query_count, document_counter.get(token, 0))
    return matched / max(len(query_tokens), 1)
