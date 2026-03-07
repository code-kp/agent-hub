const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export async function fetchAgents() {
  const response = await fetch(`${API_BASE}/api/agents`);
  if (!response.ok) {
    throw new Error(`Failed to load agents: ${response.status}`);
  }
  return response.json();
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

export async function streamChat({
  agentId,
  message,
  sessionId,
  userId = "browser-user",
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
