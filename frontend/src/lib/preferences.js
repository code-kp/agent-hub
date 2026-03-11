export const USER_ID_STORAGE_KEY = "agent-hub-user-id";
export const DEFAULT_USER_ID = "browser-user";
export const RESPONSE_STREAMING_STORAGE_KEY = "agent-hub-response-streaming";
export const DEFAULT_RESPONSE_STREAMING = true;
export const DEFAULT_MODEL_ID_STORAGE_KEY = "agent-hub-model-id";
export const LEGACY_MODEL_NAME_STORAGE_KEY = "agent-hub-model-name";

export function sanitizeUserId(value) {
  const trimmed = String(value || "").trim();
  return trimmed || DEFAULT_USER_ID;
}

export function resolveInitialUserId() {
  if (typeof window === "undefined") {
    return DEFAULT_USER_ID;
  }

  const stored = window.localStorage.getItem(USER_ID_STORAGE_KEY);
  return sanitizeUserId(stored);
}

export function normalizeResponseStreaming(value) {
  if (typeof value === "boolean") {
    return value;
  }

  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "false") {
    return false;
  }
  if (normalized === "true") {
    return true;
  }

  return DEFAULT_RESPONSE_STREAMING;
}

export function resolveInitialResponseStreaming() {
  if (typeof window === "undefined") {
    return DEFAULT_RESPONSE_STREAMING;
  }

  const stored = window.localStorage.getItem(RESPONSE_STREAMING_STORAGE_KEY);
  return normalizeResponseStreaming(stored);
}

export function sanitizeModelId(value) {
  return String(value || "").trim();
}

export function resolveInitialDefaultModelId() {
  if (typeof window === "undefined") {
    return "";
  }

  const stored = window.localStorage.getItem(DEFAULT_MODEL_ID_STORAGE_KEY);
  return sanitizeModelId(stored);
}
