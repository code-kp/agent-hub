import React from "react";

const DEFAULT_OPTIONS = [
  { label: "Auto", value: "system" },
  { label: "Light", value: "light" },
  { label: "Dark", value: "dark" },
];

export function ThemeToggle({
  value,
  onChange,
  options = DEFAULT_OPTIONS,
  ariaLabel = "Appearance mode",
}) {
  return (
    <div className="theme-toggle" role="group" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={value === option.value ? "active" : ""}
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
