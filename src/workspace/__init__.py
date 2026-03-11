"""Collaborative authoring surface for agents, tools, and skills."""

from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent
SKILLS_ROOT = WORKSPACE_ROOT / "skills"


__all__ = ["WORKSPACE_ROOT", "SKILLS_ROOT"]
