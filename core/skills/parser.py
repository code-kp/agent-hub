"""
Tests:
- tests/core/skills/test_parser.py
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from core.contracts.skills import (
    SkillDefinition,
    VALID_SKILL_CLASSES,
)


HEADING_RE = re.compile(r"^\s*#\s+(?P<title>.+?)\s*$", re.MULTILINE)


CLASSIFIED_SKILL_ROOTS = frozenset({"behavior", "knowledge"})


def build_skill_id(path: Path, skills_root: Path) -> str:
    relative = path.relative_to(skills_root)
    parts = list(relative.with_suffix("").parts)
    if parts and parts[0] in CLASSIFIED_SKILL_ROOTS:
        parts = parts[1:]
    return ".".join(part.strip() for part in parts if part.strip())


def parse_skill_file(path: Path, skills_root: Path) -> SkillDefinition:
    raw_content = path.read_text(encoding="utf-8")
    _, body = split_frontmatter(raw_content)
    normalized_body = body.strip() or raw_content.strip()
    skill_id = build_skill_id(path, skills_root)
    source = str(path.relative_to(skills_root)).replace("\\", "/")
    skill_class = infer_skill_class(path, skills_root)

    title = str(extract_title(normalized_body) or path.stem.replace("_", " ").title()).strip()
    summary = str(extract_summary(normalized_body) or title).strip()

    if not title:
        raise ValueError("Skill {skill_id} is missing a title.".format(skill_id=skill_id))
    if skill_class not in VALID_SKILL_CLASSES:
        raise ValueError(
            "Skill {skill_id} has unsupported class: {skill_class}".format(
                skill_id=skill_id,
                skill_class=skill_class,
            )
        )
    if not summary:
        raise ValueError("Skill {skill_id} is missing a summary.".format(skill_id=skill_id))

    return SkillDefinition(
        id=skill_id,
        source=source,
        path=path,
        title=title,
        summary=summary,
        skill_class=skill_class,
        body=normalized_body,
    )


def infer_skill_class(path: Path, skills_root: Path) -> str:
    relative = path.relative_to(skills_root)
    parts = [part.strip().lower() for part in relative.with_suffix("").parts if part.strip()]
    if not parts:
        raise ValueError("Skill file must live under a behavior, knowledge, or uploads folder.")
    root = parts[0]
    if root in CLASSIFIED_SKILL_ROOTS:
        return root
    if root == "uploads":
        return "knowledge"
    raise ValueError(
        "Skill {path} must live under workspace/skills/behavior, workspace/skills/knowledge, or workspace/skills/uploads."
        .format(path=str(path))
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
