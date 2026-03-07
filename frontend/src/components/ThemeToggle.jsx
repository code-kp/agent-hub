import React from "react";

export function ThemeToggle({ theme, onThemeChange }) {
  return (
    <div className="theme-toggle" role="group" aria-label="Appearance">
      <button
        type="button"
        className={theme === "light" ? "active" : ""}
        aria-pressed={theme === "light"}
        onClick={() => onThemeChange("light")}
      >
        Light
      </button>
      <button
        type="button"
        className={theme === "dark" ? "active" : ""}
        aria-pressed={theme === "dark"}
        onClick={() => onThemeChange("dark")}
      >
        Dark
      </button>
    </div>
  );
}
