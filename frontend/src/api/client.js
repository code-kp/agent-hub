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
  namespace = "",
  tags = "",
  triggers = "",
  userId = "browser-user",
}) {
  const body = new FormData();
  body.set("file", file);
  body.set("user_id", userId);
  body.set("namespace", namespace);
  body.set("tags", tags);
  body.set("triggers", triggers);

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
  instructions,
  message,
}) {
  const response = await fetch(`${API_BASE}/api/ai`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agent_id: agentId,
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
  message,
  sessionId,
  userId = "browser-user",
  history,
  stream = true,
  onEvent,
}) {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agent_id: agentId,
      message,
      session_id: sessionId,
      user_id: userId,
      history,
      stream,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with ${response.status}`);
  }

  const nextSessionId = response.headers.get("X-Session-Id") || sessionId || null;

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

  return { sessionId: nextSessionId };
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
