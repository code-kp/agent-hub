from __future__ import annotations

import core.contracts.agent as contracts_agent
import core.execution.direct.runtime as direct_runtime
import core.execution.orchestrated.runtime as orchestrated_runtime
import core.execution.shared.types as shared_types
import core.registry as registry


def create_agent_runtime(
    record: shared_types.AgentRecord,
    *,
    runtime_mode: str | None = None,
    model_name: str | None = None,
):
    definition = registry.Register.get(contracts_agent.Agent, record.agent_name)
    resolved_runtime_mode = contracts_agent.normalize_runtime_mode(
        runtime_mode or getattr(definition, "runtime_mode", "direct")
    )
    if resolved_runtime_mode == "orchestrated":
        return orchestrated_runtime.OrchestratedAgentRuntime(
            record,
            model_name_override=model_name,
        )
    return direct_runtime.DirectAgentRuntime(record, model_name_override=model_name)
