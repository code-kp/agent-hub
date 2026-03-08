import React from "react";

import { ThemeToggle } from "./ThemeToggle";

const STREAMING_OPTIONS = [
  { label: "On", value: "on" },
  { label: "Off", value: "off" },
];

export function ResponseStreamingCard({
  enabled,
  onChange,
}) {
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
    </section>
  );
}
