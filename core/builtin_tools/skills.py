from __future__ import annotations

from core.contracts.tools import ToolModule, register_tool_class
from core.skills.context import current_skill_store


@register_tool_class
class SearchSkillsTool(ToolModule):
    name = "search_skills"
    description = "Search relevant markdown skill chunks for a query."
    category = "internal_guidance"
    use_when = (
        "The answer likely depends on internal guidance, workflows, policy, or product reference material.",
        "You need to find the most relevant skill excerpts before answering.",
    )
    avoid_when = (
        "Fresh public information is required from the web.",
    )
    returns = "Relevant skill chunks with ids, headings, and text excerpts."
    follow_up_tools = ("read_skill_file",)

    def run(self, query: str, max_results: int = 3) -> dict:
        store = current_skill_store()
        store.refresh()
        self.progress.think(
            "Looking through internal guidance",
            detail="Searching the shared guidance library for the most relevant sections.",
            step_id="search_skills",
        )
        self.progress.debug("Searching indexed skill chunks.", query=query, max_results=max_results)
        results = store.search(query=query, max_results=max_results)
        self.progress.think(
            "Relevant guidance found",
            detail="Found {count} likely match(es) in the shared guidance library.".format(count=len(results)),
            step_id="search_skills",
            state="done",
        )
        self.progress.debug("Skill search completed.", matches=len(results))
        return {"query": query, "results": results}


@register_tool_class
class ListSkillFilesTool(ToolModule):
    name = "list_skill_files"
    description = "List discovered skills with their ids, classes, and summaries."
    category = "internal_guidance"
    use_when = (
        "You need to inspect what internal guidance exists before selecting one.",
    )
    returns = "A list of discovered skills with ids, classes, and summaries."

    def run(self) -> dict:
        store = current_skill_store()
        store.refresh()
        self.progress.think(
            "Reviewing available guidance",
            detail="Listing the shared guidance that can be used for this request.",
            step_id="list_skill_files",
        )
        skills = store.describe()
        self.progress.think(
            "Available guidance reviewed",
            detail="Found {count} shared skill definition(s).".format(count=len(skills)),
            step_id="list_skill_files",
            state="done",
        )
        self.progress.debug("Listed discovered skills.", skills=len(skills))
        return {"skills": skills}


@register_tool_class
class ReadSkillFileTool(ToolModule):
    name = "read_skill_file"
    description = "Read a markdown skill by skill id or relative file path."
    category = "internal_guidance"
    use_when = (
        "A specific skill has already been identified and you need its full content.",
    )
    returns = "The selected skill metadata plus full markdown content."

    def run(self, file_name: str) -> dict:
        store = current_skill_store()
        store.refresh()
        skill = store.get_skill(file_name) or store.get_skill_by_source(file_name)
        if skill is None:
            raise FileNotFoundError("Skill not found: {name}".format(name=file_name))
        self.progress.think(
            "Opening the relevant guidance",
            detail="Reading the exact guidance that looks most useful for this request.",
            step_id="read_skill_file",
        )
        self.progress.debug("Reading skill file.", file=skill.source, skill_id=skill.id)
        self.progress.think(
            "Guidance reviewed",
            detail="The relevant guidance is ready to be folded into the answer.",
            step_id="read_skill_file",
            state="done",
        )
        return {
            "skill": {
                "id": skill.id,
                "title": skill.title,
                "class": skill.skill_class,
                "summary": skill.summary,
                "source": skill.source,
            },
            "content": skill.body,
        }
