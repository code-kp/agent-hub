from __future__ import annotations

from importlib import import_module


__all__ = [
    "ResolvedSkillContext",
    "SkillChunk",
    "SkillResolver",
    "SkillStore",
    "bind_skill_store",
    "build_user_upload_scope",
    "create_uploaded_skill",
    "current_skill_store",
    "describe_resolved_skill_context",
    "parse_skill_file",
    "reset_skill_store",
    "serialize_resolved_skills",
]


_EXPORTS = {
    "bind_skill_store": ("core.skills.context", "bind_skill_store"),
    "current_skill_store": ("core.skills.context", "current_skill_store"),
    "reset_skill_store": ("core.skills.context", "reset_skill_store"),
    "parse_skill_file": ("core.skills.parser", "parse_skill_file"),
    "ResolvedSkillContext": ("core.skills.resolver", "ResolvedSkillContext"),
    "SkillResolver": ("core.skills.resolver", "SkillResolver"),
    "describe_resolved_skill_context": (
        "core.skills.resolver",
        "describe_resolved_skill_context",
    ),
    "serialize_resolved_skills": ("core.skills.resolver", "serialize_resolved_skills"),
    "SkillChunk": ("core.skills.store", "SkillChunk"),
    "SkillStore": ("core.skills.store", "SkillStore"),
    "build_user_upload_scope": ("core.skills.uploads", "build_user_upload_scope"),
    "create_uploaded_skill": ("core.skills.uploads", "create_uploaded_skill"),
}


def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute_name = target
    module = import_module(module_name)
    return getattr(module, attribute_name)
