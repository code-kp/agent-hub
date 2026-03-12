export const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

const AGENTS_TIMEOUT_MS = 6500;
const HEALTH_TIMEOUT_MS = 2500;

function formatTimeoutMessage(label, timeoutMs) {
  return `${label} timed out after ${Math.ceil(timeoutMs / 1000)}s.`;
}

async function fetchWithTimeout(url, { timeoutMs, ...options } = {}) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => {
    controller.abort();
  }, timeoutMs);

  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(formatTimeoutMessage("Request", timeoutMs));
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function readResponsePayload(response) {
  const text = await response.text().catch(() => "");
  if (!text) {
    return {};
  }

  try {
    return JSON.parse(text);
  } catch {
    return { text };
  }
}

export async function fetchAgents({ timeoutMs = AGENTS_TIMEOUT_MS } = {}) {
  const response = await fetchWithTimeout(`${API_BASE}/api/agents`, { timeoutMs });
  const payload = await readResponsePayload(response);

  if (!response.ok) {
    throw new Error(payload.detail || payload.message || payload.text || `Failed to load agents: ${response.status}`);
  }

  return payload;
}

export async function fetchModels({ timeoutMs = AGENTS_TIMEOUT_MS } = {}) {
  const response = await fetchWithTimeout(`${API_BASE}/api/models`, { timeoutMs });
  const payload = await readResponsePayload(response);

  if (!response.ok) {
    throw new Error(payload.detail || payload.message || payload.text || `Failed to load models: ${response.status}`);
  }

  return payload;
}

export async function fetchConversations({
  userId = "browser-user",
  timeoutMs = AGENTS_TIMEOUT_MS,
} = {}) {
  const query = new URLSearchParams({ user_id: userId });
  const response = await fetchWithTimeout(
    `${API_BASE}/api/conversations?${query.toString()}`,
    { timeoutMs },
  );
  const payload = await readResponsePayload(response);

  if (!response.ok) {
    throw new Error(payload.detail || payload.message || payload.text || `Failed to load conversations: ${response.status}`);
  }

  return payload;
}

export async function fetchConversationSession({
  userId = "browser-user",
  conversationId,
  agentId,
  mode,
  modelId,
  modelName,
  timeoutMs = AGENTS_TIMEOUT_MS,
} = {}) {
  const query = new URLSearchParams({
    user_id: userId,
    conversation_id: conversationId || "",
    agent_id: agentId || "",
  });
  if (mode) {
    query.set("mode", mode);
  }
  if (modelId) {
    query.set("model_id", modelId);
  }
  if (modelName) {
    query.set("model_name", modelName);
  }

  const response = await fetchWithTimeout(
    `${API_BASE}/api/conversations/session?${query.toString()}`,
    { timeoutMs },
  );
  const payload = await readResponsePayload(response);

  if (!response.ok) {
    throw new Error(payload.detail || payload.message || payload.text || `Failed to load session: ${response.status}`);
  }

  return payload;
}

export async function saveConversations({
  userId = "browser-user",
  chats = [],
}) {
  const response = await fetch(`${API_BASE}/api/conversations`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      chats,
    }),
  });

  const payload = await readResponsePayload(response);
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || payload.text || `Failed to save conversations: ${response.status}`);
  }

  return payload;
}

export async function fetchHealth({ timeoutMs = HEALTH_TIMEOUT_MS } = {}) {
  try {
    const response = await fetchWithTimeout(`${API_BASE}/api/health`, { timeoutMs });
    const payload = await readResponsePayload(response);

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        message: payload.detail || payload.message || `Health check failed with ${response.status}.`,
      };
    }

    return {
      ok: Boolean(payload.ok),
      status: response.status,
      message: payload.ok
        ? "Agent service is responding."
        : `Health check reached ${API_BASE}/api/health but did not return ok.`,
    };
  } catch (error) {
    if (error?.name === "AbortError" || /timed out/i.test(error?.message || "")) {
      return {
        ok: false,
        status: 0,
        message: `Agent service did not respond at ${API_BASE}/api/health.`,
      };
    }

    return {
      ok: false,
      status: 0,
      message: error?.message || `Could not reach ${API_BASE}/api/health.`,
    };
  }
}

export async function uploadSkillFile({
  file,
  skillClass = "knowledge",
  namespace = "",
  userId = "browser-user",
}) {
  const body = new FormData();
  body.set("file", file);
  body.set("skill_class", skillClass);
  body.set("user_id", userId);
  body.set("namespace", namespace);

  const response = await fetch(`${API_BASE}/api/skills/upload`, {
    method: "POST",
    body,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Upload failed with ${response.status}`);
  }

  return payload;
}

export async function invokeAi({
  agentId,
  modelId,
  modelName,
  instructions,
  message,
}) {
  const response = await fetch(`${API_BASE}/api/ai`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agent_id: agentId,
      model_id: modelId,
      model_name: modelName,
      instructions,
      message,
    }),
  });

  const payload = await readResponsePayload(response);
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || payload.text || `AI request failed with ${response.status}`);
  }

  return payload.text || "";
}

export async function streamChat({
  agentId,
  mode,
  modelId,
  modelName,
  conversationId,
  message,
  teamAgentIds,
  userId = "browser-user",
  stream = true,
  onEvent,
}) {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agent_id: agentId,
      mode,
      model_id: modelId,
      model_name: modelName,
      conversation_id: conversationId,
      message,
      team_agent_ids: Array.isArray(teamAgentIds) ? teamAgentIds : undefined,
      user_id: userId,
      stream,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with ${response.status}`);
  }

  const resolvedMode = response.headers.get("X-Mode") || mode || "direct";
  const resolvedSessionId = response.headers.get("X-Session-Id") || null;

  if (!response.body) {
    throw new Error("Streaming body unavailable in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const parsed = parseSseFrame(frame);
      if (parsed) {
        onEvent(parsed.type, parsed.payload);
      }
    }
  }

  return { mode: resolvedMode, sessionId: resolvedSessionId };
}

function parseSseFrame(frame) {
  let type = "message";
  const dataLines = [];

  for (const rawLine of frame.split("\n")) {
    const line = rawLine.trimEnd();
    if (!line) {
      continue;
    }
    if (line.startsWith("event:")) {
      type = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (!dataLines.length) {
    return null;
  }

  try {
    return {
      type,
      payload: JSON.parse(dataLines.join("\n")),
    };
  } catch (error) {
    return {
      type: "error",
      payload: { message: "Failed to parse stream payload." },
    };
  }
}
