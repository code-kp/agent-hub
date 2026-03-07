from __future__ import annotations

from core.contracts.tools import current_progress, tool
from core.skills.store import SkillStore
from workspace import SKILLS_ROOT


SKILL_STORE = SkillStore(SKILLS_ROOT)


@tool(
    description="Search relevant markdown skill chunks for a query.",
    category="internal_guidance",
    use_when=(
        "The answer likely depends on internal guidance, workflows, policy, or product reference material.",
        "You need to find the most relevant skill excerpts before answering.",
    ),
    avoid_when=(
        "Fresh public information is required from the web.",
    ),
    returns="Relevant skill chunks with ids, headings, and text excerpts.",
    follow_up_tools=("read_skill_file",),
)
def search_skills(query: str, max_results: int = 3) -> dict:
    progress = current_progress()
    progress.think(
        "Looking through internal guidance",
        detail="Searching the shared guidance library for the most relevant sections.",
        step_id="search_skills",
    )
    progress.debug("Searching indexed skill chunks.", query=query, max_results=max_results)
    results = SKILL_STORE.search(query=query, max_results=max_results)
    progress.think(
        "Relevant guidance found",
        detail="Found {count} likely match(es) in the shared guidance library.".format(count=len(results)),
        step_id="search_skills",
        state="done",
    )
    progress.debug("Skill search completed.", matches=len(results))
    return {"query": query, "results": results}


@tool(
    description="List discovered skills with their ids, types, and summaries.",
    category="internal_guidance",
    use_when=(
        "You need to inspect what internal guidance exists before selecting one.",
    ),
    returns="A list of discovered skills with ids, types, modes, and summaries.",
)
def list_skill_files() -> dict:
    progress = current_progress()
    progress.think(
        "Reviewing available guidance",
        detail="Listing the shared guidance that can be used for this request.",
        step_id="list_skill_files",
    )
    skills = SKILL_STORE.describe()
    progress.think(
        "Available guidance reviewed",
        detail="Found {count} shared skill definition(s).".format(count=len(skills)),
        step_id="list_skill_files",
        state="done",
    )
    progress.debug("Listed discovered skills.", skills=len(skills))
    return {"skills": skills}


@tool(
    description="Read a markdown skill by skill id or relative file path.",
    category="internal_guidance",
    use_when=(
        "A specific skill has already been identified and you need its full content.",
    ),
    returns="The selected skill metadata plus full markdown content.",
)
def read_skill_file(file_name: str) -> dict:
    progress = current_progress()
    skill = SKILL_STORE.get_skill(file_name) or SKILL_STORE.get_skill_by_source(file_name)
    if skill is None:
        raise FileNotFoundError("Skill not found: {name}".format(name=file_name))
    progress.think(
        "Opening the relevant guidance",
        detail="Reading the exact guidance that looks most useful for this request.",
        step_id="read_skill_file",
    )
    progress.debug("Reading skill file.", file=skill.source, skill_id=skill.id)
    progress.think(
        "Guidance reviewed",
        detail="The relevant guidance is ready to be folded into the answer.",
        step_id="read_skill_file",
        state="done",
    )
    return {
        "skill": {
            "id": skill.id,
            "title": skill.title,
            "type": skill.skill_type,
            "summary": skill.summary,
            "mode": skill.mode,
            "source": skill.source,
        },
        "content": skill.body,
    }


__all__ = ["search_skills", "list_skill_files", "read_skill_file"]
