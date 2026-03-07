from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.contracts.skills import (
    SkillDefinition,
    VALID_SKILL_MODES,
    VALID_SKILL_TYPES,
)


HEADING_RE = re.compile(r"^\s*#\s+(?P<title>.+?)\s*$", re.MULTILINE)


def build_skill_id(path: Path, skills_root: Path) -> str:
    relative = path.relative_to(skills_root)
    parts = list(relative.with_suffix("").parts)
    return ".".join(part.strip() for part in parts if part.strip())


def parse_skill_file(path: Path, skills_root: Path) -> SkillDefinition:
    raw_content = path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(raw_content)
    metadata = parse_frontmatter(frontmatter)
    skill_id = build_skill_id(path, skills_root)
    source = str(path.relative_to(skills_root)).replace("\\", "/")

    title = str(metadata.get("title") or extract_title(body) or path.stem.replace("_", " ").title()).strip()
    skill_type = str(metadata.get("type") or "knowledge").strip().lower()
    mode = str(metadata.get("mode") or "auto").strip().lower()
    summary = str(metadata.get("summary") or extract_summary(body)).strip()
    tags = tuple(_coerce_string_list(metadata.get("tags")))
    triggers = tuple(_coerce_string_list(metadata.get("triggers")))
    requires_tools = tuple(_coerce_string_list(metadata.get("requires_tools")))
    priority = _coerce_int(metadata.get("priority"), default=50)

    if not title:
        raise ValueError("Skill {skill_id} is missing a title.".format(skill_id=skill_id))
    if skill_type not in VALID_SKILL_TYPES:
        raise ValueError(
            "Skill {skill_id} has unsupported type: {skill_type}".format(
                skill_id=skill_id,
                skill_type=skill_type,
            )
        )
    if mode not in VALID_SKILL_MODES:
        raise ValueError(
            "Skill {skill_id} has unsupported mode: {mode}".format(
                skill_id=skill_id,
                mode=mode,
            )
        )
    if not summary:
        raise ValueError("Skill {skill_id} is missing a summary.".format(skill_id=skill_id))

    return SkillDefinition(
        id=skill_id,
        source=source,
        path=path,
        title=title,
        skill_type=skill_type,
        summary=summary,
        tags=tags,
        triggers=triggers,
        mode=mode,
        priority=priority,
        requires_tools=requires_tools,
        body=body.strip(),
    )


def split_frontmatter(content: str) -> Tuple[str, str]:
    if not content.startswith("---\n"):
        return "", content

    lines = content.splitlines()
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            frontmatter = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :]).lstrip("\n")
            return frontmatter, body
    return "", content


def parse_frontmatter(frontmatter: str) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    if not frontmatter.strip():
        return values

    lines = frontmatter.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        index += 1

        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in raw_line:
            raise ValueError("Invalid skill frontmatter line: {line}".format(line=raw_line))

        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError("Skill frontmatter contains an empty key.")

        if value:
            values[key] = _parse_value(value)
            continue

        list_items: List[Any] = []
        while index < len(lines):
            candidate = lines[index]
            if not candidate.startswith("  - ") and not candidate.startswith("\t- "):
                break
            item = candidate.split("-", 1)[1].strip()
            list_items.append(_parse_value(item))
            index += 1

        values[key] = list_items

    return values


def extract_title(body: str) -> str:
    match = HEADING_RE.search(body or "")
    if not match:
        return ""
    return " ".join(match.group("title").split())


def extract_summary(body: str) -> str:
    paragraph_lines: List[str] = []
    for raw_line in (body or "").splitlines():
        line = raw_line.strip()
        if not line:
            if paragraph_lines:
                break
            continue
        if line.startswith("#"):
            continue
        paragraph_lines.append(line)
    return " ".join(paragraph_lines[:3]).strip()


def _parse_value(value: str) -> Any:
    text = value.strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_strip_quotes(item.strip()) for item in inner.split(",") if item.strip()]
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered.lstrip("-").isdigit():
        return int(lowered)
    return _strip_quotes(text)


def _strip_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _coerce_string_list(value: Any) -> List[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = [value]
    result: List[str] = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _coerce_int(value: Any, *, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
