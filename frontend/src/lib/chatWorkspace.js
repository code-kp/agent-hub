function createMessageBase(role, metadata = {}) {
  return {
    id: crypto.randomUUID(),
    role,
    text: "",
    streaming: role === "assistant",
    createdAt: Date.now(),
    ...metadata,
  };
}

export function createUserMessage(text, metadata = {}) {
  return {
    ...createMessageBase("user", metadata),
    text,
    streaming: false,
  };
}

export function createAssistantMessage(metadata = {}) {
  return {
    ...createMessageBase("assistant", metadata),
    thinking: [],
    thinkingActive: true,
  };
}

function formatToolEvent(type, payload) {
  if (type === "thinking_step") {
    const label = payload.label || "Working through the request";
    const detail = payload.detail || "";
    return detail ? `${label}\n${detail}` : label;
  }
  if (type === "tool_selection_reason") {
    return `${payload.tool_name || "tool"}\n${payload.reason || "Selected by model."}`;
  }
  if (type === "tool_started") {
    return `${payload.tool_name}\n${JSON.stringify(payload.args || {}, null, 2)}`;
  }
  if (type === "tool_completed") {
    return `${payload.tool_name}\n${JSON.stringify(payload.response || {}, null, 2)}`;
  }
  if (type === "skill_context_selected") {
    const chunks = payload.chunks || [];
    if (!chunks.length) {
      return "No relevant skill chunks selected.";
    }
    return chunks
      .map((chunk) => `${chunk.source} -> ${chunk.heading}\n${chunk.preview}`)
      .join("\n\n");
  }
  return null;
}

export function formatEventBody(type, payload) {
  if (payload.display_text) {
    return payload.display_text;
  }
  if (payload.message) {
    return payload.message;
  }

  const toolEventBody = formatToolEvent(type, payload);
  if (toolEventBody) {
    return toolEventBody;
  }

  if (type === "error") {
    return payload.message || "Unknown error";
  }

  return JSON.stringify(payload, null, 2);
}

export function createThinkingEvent(type, payload = {}) {
  return {
    id: crypto.randomUUID(),
    stepId: payload.step_id || "",
    type,
    channel: payload.channel || "thinking",
    label: payload.label || "",
    detail: payload.detail || "",
    state: payload.state || "",
    body: formatEventBody(type, payload),
    timestamp: payload.timestamp,
  };
}

export function normalizeAgentTree(nodes, wrapRootAgents = true) {
  const rootAgents = [];
  const namespaces = [];

  nodes.forEach((node) => {
    if (node.type === "agent") {
      rootAgents.push(node);
      return;
    }

    namespaces.push({
      ...node,
      children: normalizeAgentTree(node.children || [], false),
    });
  });

  if (!wrapRootAgents || !rootAgents.length) {
    return [...rootAgents, ...namespaces];
  }

  return [
    {
      type: "namespace",
      name: "workspace",
      children: rootAgents,
    },
    ...namespaces,
  ];
}

export function filterTree(nodes, query) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return nodes;
  }

  const result = [];

  for (const node of nodes) {
    if (node.type === "namespace") {
      const children = filterTree(node.children || [], normalized);
      if (children.length || (node.name || "").toLowerCase().includes(normalized)) {
        result.push({
          ...node,
          children,
        });
      }
      continue;
    }

    const fields = [node.name || "", node.id || "", node.description || ""];
    if (fields.some((value) => value.toLowerCase().includes(normalized))) {
      result.push(node);
    }
  }

  return result;
}

export function buildChatTitle(agentId, agents, chats, excludeChatId = "") {
  const base = agents.find((item) => item.id === agentId)?.name || agentId || "Conversation";
  const count = chats.filter(
    (chat) => chat.agentId === agentId && chat.id !== excludeChatId,
  ).length;

  return count > 0 ? `${base} ${count + 1}` : base;
}

export function createChat(agentId, agents, chats) {
  return {
    id: crypto.randomUUID(),
    title: buildChatTitle(agentId, agents, chats),
    titleSource: "default",
    agentId,
    sessionIds: {},
    messages: [],
    updatedAt: Date.now(),
  };
}

export function serializeConversationHistory(messages, limit = 8) {
  return messages
    .filter((message) => ["user", "assistant"].includes(message.role) && String(message.text || "").trim())
    .slice(-limit)
    .map((message) => ({
      role: message.role,
      text: String(message.text || "").trim(),
    }));
}
