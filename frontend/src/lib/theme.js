export const THEME_MODE_STORAGE_KEY = "agent-hub-theme-mode";
export const DEFAULT_THEME_MODE = "system";

const SYSTEM_THEME_QUERY = "(prefers-color-scheme: dark)";

export function resolveThemeMode(mode) {
  if (mode === "light" || mode === "dark") {
    return mode;
  }

  if (typeof window === "undefined") {
    return "light";
  }

  return window.matchMedia(SYSTEM_THEME_QUERY).matches ? "dark" : "light";
}

export function resolveInitialThemeMode() {
  if (typeof window === "undefined") {
    return DEFAULT_THEME_MODE;
  }

  const storedMode = window.localStorage.getItem(THEME_MODE_STORAGE_KEY);
  return storedMode === "light" || storedMode === "dark" || storedMode === "system"
    ? storedMode
    : DEFAULT_THEME_MODE;
}

export function applyTheme(mode = DEFAULT_THEME_MODE) {
  if (typeof document === "undefined") {
    return;
  }

  const resolvedTheme = resolveThemeMode(mode);
  const root = document.documentElement;
  root.dataset.theme = resolvedTheme;
  root.dataset.themeMode = mode;
  root.style.colorScheme = resolvedTheme;
}
