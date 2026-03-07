from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

from core.contracts.skills import VALID_SKILL_MODES, VALID_SKILL_TYPES, SkillDefinition
from core.skills.parser import (
    extract_summary,
    extract_title,
    parse_frontmatter,
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
    title: str | None = None,
    summary: str | None = None,
    skill_type: str = "knowledge",
    mode: str = "auto",
    tags: Sequence[str] = (),
    triggers: Sequence[str] = (),
    priority: int = 60,
) -> SkillDefinition:
    normalized_type = str(skill_type or "knowledge").strip().lower()
    if normalized_type not in VALID_SKILL_TYPES:
        raise ValueError(
            "Unsupported skill type: {skill_type}. Choose one of: {allowed}.".format(
                skill_type=skill_type,
                allowed=", ".join(sorted(VALID_SKILL_TYPES)),
            )
        )

    normalized_mode = str(mode or "auto").strip().lower()
    if normalized_mode not in VALID_SKILL_MODES:
        raise ValueError(
            "Unsupported skill mode: {mode}. Choose one of: {allowed}.".format(
                mode=mode,
                allowed=", ".join(sorted(VALID_SKILL_MODES)),
            )
        )

    cleaned_content = str(content or "").replace("\r\n", "\n").strip()
    if not cleaned_content:
        raise ValueError("Uploaded markdown is empty.")

    frontmatter, body = split_frontmatter(cleaned_content)
    metadata = parse_frontmatter(frontmatter)
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
        str(title or "").strip()
        or str(metadata.get("title") or "").strip()
        or extract_title(normalized_body)
        or stem.replace("_", " ").replace("-", " ").title()
        or "Uploaded Skill"
    )
    resolved_summary = (
        str(summary or "").strip()
        or str(metadata.get("summary") or "").strip()
        or extract_summary(normalized_body)
        or "User-uploaded markdown knowledge."
    )

    normalized_tags = _merge_values(
        metadata.get("tags"),
        tags,
        ("uploaded", owner_slug),
        namespace_parts,
    )
    normalized_triggers = _merge_values(metadata.get("triggers"), triggers)
    resolved_priority = _coerce_int(metadata.get("priority"), default=priority)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        _render_skill_markdown(
            title=resolved_title,
            summary=resolved_summary,
            skill_type=normalized_type,
            mode=normalized_mode,
            tags=normalized_tags,
            triggers=normalized_triggers,
            priority=resolved_priority,
            body=normalized_body,
        ),
        encoding="utf-8",
    )

    return parse_skill_file(target_path, skills_root)


def _render_skill_markdown(
    *,
    title: str,
    summary: str,
    skill_type: str,
    mode: str,
    tags: Sequence[str],
    triggers: Sequence[str],
    priority: int,
    body: str,
) -> str:
    lines = [
        "---",
        "title: {title}".format(title=_quote_yaml(title)),
        "type: {skill_type}".format(skill_type=skill_type),
        "summary: {summary}".format(summary=_quote_yaml(summary)),
        "tags: [{tags}]".format(tags=", ".join(_quote_yaml(value) for value in tags)),
        "triggers: [{triggers}]".format(
            triggers=", ".join(_quote_yaml(value) for value in triggers)
        ),
        "mode: {mode}".format(mode=mode),
        "priority: {priority}".format(priority=priority),
        "---",
        "",
        body.strip(),
        "",
    ]
    return "\n".join(lines)


def _normalize_namespace(namespace: str) -> tuple[str, ...]:
    parts = []
    for raw_part in str(namespace or "").replace("\\", "/").split("/"):
        slug = _slugify(raw_part)
        if slug:
            parts.append(slug)
    return tuple(parts)


def normalize_uploader_id(uploader_id: str, *, fallback: str = DEFAULT_UPLOAD_USER_ID) -> str:
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


def _merge_values(*value_groups: object) -> tuple[str, ...]:
    values = []
    seen = set()
    for group in value_groups:
        if group in (None, "", (), [], set()):
            continue
        if isinstance(group, (list, tuple, set)):
            items: Iterable[object] = group
        else:
            items = (group,)
        for item in items:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            values.append(text)
    return tuple(values)


def _quote_yaml(value: str) -> str:
    text = str(value or "").strip().replace('"', '\\"')
    return '"{text}"'.format(text=text)


def _coerce_int(value: object, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
