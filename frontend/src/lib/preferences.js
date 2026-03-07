export const USER_ID_STORAGE_KEY = "agent-hub-user-id";
export const DEFAULT_USER_ID = "browser-user";

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
