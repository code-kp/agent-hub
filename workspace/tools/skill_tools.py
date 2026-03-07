from __future__ import annotations

from core.interfaces.tools import current_progress, tool
from core.skill_store import SkillStore
from workspace import SKILLS_ROOT


SKILL_STORE = SkillStore(SKILLS_ROOT)


@tool(description="Search relevant markdown skill chunks for a query.")
def search_skills(query: str, max_results: int = 3) -> dict:
    progress = current_progress()
    progress.comment("Searching indexed skill chunks.", query=query, max_results=max_results)
    results = SKILL_STORE.search(query=query, max_results=max_results)
    progress.comment("Skill search completed.", matches=len(results))
    return {"query": query, "results": results}


@tool(description="List indexed markdown skill files.")
def list_skill_files() -> dict:
    progress = current_progress()
    files = SKILL_STORE.describe()
    progress.comment("Listed indexed skill files.", files=len(files))
    return {"skills": files}


@tool(description="Read a markdown skill file by relative path.")
def read_skill_file(file_name: str) -> dict:
    progress = current_progress()
    root = SKILL_STORE.skills_dir.resolve()
    path = (SKILL_STORE.skills_dir / file_name).resolve()
    if root not in path.parents and path != root:
        raise ValueError("Requested file is outside the configured skill directory.")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("Skill file not found: {name}".format(name=file_name))
    progress.comment("Reading skill file.", file=file_name)
    return {"file": file_name, "content": path.read_text(encoding="utf-8")}


__all__ = ["search_skills", "list_skill_files", "read_skill_file"]
