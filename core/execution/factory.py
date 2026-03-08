from __future__ import annotations

import core.contracts.agent as contracts_agent
import core.execution.direct.runtime as direct_runtime
import core.execution.orchestrated.runtime as orchestrated_runtime
import core.execution.shared.types as shared_types
import core.registry as registry


def create_agent_runtime(record: shared_types.AgentRecord):
    definition = registry.Register.get(contracts_agent.Agent, record.agent_name)
    if getattr(definition, "runtime_mode", "direct") == "orchestrated":
        return orchestrated_runtime.OrchestratedAgentRuntime(record)
    return direct_runtime.DirectAgentRuntime(record)
