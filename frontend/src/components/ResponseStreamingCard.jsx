import React from "react";

import { ThemeToggle } from "./ThemeToggle";

const STREAMING_OPTIONS = [
  { label: "On", value: "on" },
  { label: "Off", value: "off" },
];

export function ResponseStreamingCard({
  enabled,
  onChange,
  defaultModelId,
  modelOptions,
  modelsLoading,
  onDefaultModelIdChange,
}) {
  const selectedDefaultModel = modelOptions.find((item) => item.id === defaultModelId) || null;
  const modelChipLabel = selectedDefaultModel ? selectedDefaultModel.label : "Backend default";

  return (
    <section className="settings-card">
      <div className="settings-card-header">
        <div>
          <h3>Response streaming</h3>
          <p>Stream the final answer into the chat as it is generated, or wait for the full reply.</p>
        </div>
        <span className="settings-chip">{enabled ? "On" : "Off"}</span>
      </div>

      <ThemeToggle
        value={enabled ? "on" : "off"}
        onChange={(value) => onChange(value === "on")}
        options={STREAMING_OPTIONS}
        ariaLabel="Response streaming"
      />

      <p className="settings-helper-text">
        Thinking and tool progress keep updating live either way. This only changes whether the final answer text arrives token by token.
      </p>

      <div className="settings-divider" />

      <div className="settings-card-header">
        <div>
          <h3>Default model</h3>
          <p>Used whenever the chat model picker is left on its default setting.</p>
        </div>
        <span className="settings-chip">{modelChipLabel}</span>
      </div>

      <label className="settings-field">
        <span>Model</span>
        <div className="settings-select-shell">
          <span className="settings-select-icon" aria-hidden="true">
            <svg viewBox="0 0 16 16">
              <path
                d="M8 1.5l1.55 3.16 3.45.5-2.5 2.43.59 3.41L8 9.39 4.91 11l.59-3.41L3 5.16l3.45-.5L8 1.5z"
                fill="none"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.15"
              />
            </svg>
          </span>
          <select
            value={defaultModelId}
            disabled={modelsLoading}
            aria-label="Choose default model"
            onChange={(event) => onDefaultModelIdChange(event.target.value)}
          >
            <option value="">Backend default</option>
            {modelOptions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
          <span className="settings-select-chevron" aria-hidden="true">
            <svg viewBox="0 0 16 16">
              <path
                d="M4.25 6.25L8 10l3.75-3.75"
                fill="none"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.5"
              />
            </svg>
          </span>
        </div>
        <small>
          Pick one of the backend-supported models here. The chat composer can still
          temporarily switch away from this default.
        </small>
      </label>
    </section>
  );
}
