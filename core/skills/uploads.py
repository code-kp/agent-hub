"""
Tests:
- tests/core/skills/test_uploads.py
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from core.contracts.skills import SkillDefinition
from core.skills.parser import (
    extract_summary,
    extract_title,
    parse_skill_file,
    split_frontmatter,
)


UPLOAD_NAMESPACE = "uploads"
DEFAULT_UPLOAD_USER_ID = "browser-user"
SLUG_RE = re.compile(r"[^a-z0-9]+")


def create_uploaded_skill(
    *,
    skills_root: Path,
    file_name: str,
    content: str,
    uploader_id: str,
    namespace: str = "",
) -> SkillDefinition:
    cleaned_content = str(content or "").replace("\r\n", "\n").strip()
    if not cleaned_content:
        raise ValueError("Uploaded markdown is empty.")

    _, body = split_frontmatter(cleaned_content)
    normalized_body = body.strip() or cleaned_content

    stem = Path(file_name or "uploaded-skill.md").stem
    owner_slug = normalize_uploader_id(uploader_id)
    file_slug = _slugify(stem)
    namespace_parts = _normalize_namespace(namespace)

    target_path = skills_root / UPLOAD_NAMESPACE / owner_slug
    for part in namespace_parts:
        target_path /= part
    target_path = target_path / "{slug}.md".format(slug=file_slug)

    resolved_title = (
        extract_title(normalized_body)
        or stem.replace("_", " ").replace("-", " ").title()
        or "Uploaded Skill"
    )
    resolved_summary = extract_summary(normalized_body)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        _render_skill_markdown(
            title=resolved_title, summary=resolved_summary, body=normalized_body
        ),
        encoding="utf-8",
    )

    return parse_skill_file(target_path, skills_root)


def _render_skill_markdown(
    *,
    title: str,
    summary: str,
    body: str,
) -> str:
    normalized_body = body.strip()
    has_heading = bool(extract_title(normalized_body))
    lines = []
    if not has_heading:
        lines.extend(["# {title}".format(title=title), ""])
        if summary and summary not in normalized_body:
            lines.extend([summary, ""])
    lines.append(normalized_body)
    lines.append("")
    return "\n".join(lines)


def _normalize_namespace(namespace: str) -> tuple[str, ...]:
    parts = []
    for raw_part in str(namespace or "").replace("\\", "/").split("/"):
        slug = _slugify(raw_part)
        if slug:
            parts.append(slug)
    return tuple(parts)


def normalize_uploader_id(
    uploader_id: str, *, fallback: str = DEFAULT_UPLOAD_USER_ID
) -> str:
    slug = _slugify(uploader_id)
    if slug:
        return slug
    fallback_slug = _slugify(fallback)
    return fallback_slug or DEFAULT_UPLOAD_USER_ID


def build_user_upload_scope(user_id: str) -> str:
    return "{namespace}.{user_id}".format(
        namespace=UPLOAD_NAMESPACE,
        user_id=normalize_uploader_id(user_id),
    )


def _slugify(value: str) -> str:
    text = str(value or "").strip().lower()
    text = SLUG_RE.sub("-", text)
    return text.strip("-")
