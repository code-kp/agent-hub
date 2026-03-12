from __future__ import annotations

from core.contracts.tools import ToolModule, register_tool_class


@register_tool_class
class UsersTechnology(ToolModule):
    name = "users_technology"
    description = "Describe what users_technology should do."
    category = "general"
    use_when = (
        "The agent needs data or side effects that are not already available in skills or conversation context.",
    )
    returns = "A JSON payload with the requested result."

    def run(self, query: str) -> dict:
        self.progress.think("Starting users_technology", detail="Replace this scaffold with the real integration.", step_id="users_technology")
        raise NotImplementedError("Implement users_technology before using this tool.")
