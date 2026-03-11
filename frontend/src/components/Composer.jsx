import React, { useEffect, useRef, useState } from "react";

export function Composer({
  disabled,
  isSending,
  hasAgent,
  agentName,
  orchestrationAvailable,
  defaultModelId,
  modelId,
  modelOptions,
  modelsLoading,
  runtimeMode,
  onModelIdChange,
  onSetRuntimeMode,
  onSend,
}) {
  const [value, setValue] = useState("");
  const textareaRef = useRef(null);

  useEffect(() => {
    if (!textareaRef.current) {
      return;
    }
    textareaRef.current.style.height = "0px";
    const nextHeight = Math.min(Math.max(textareaRef.current.scrollHeight, 72), 220);
    textareaRef.current.style.height = `${nextHeight}px`;
  }, [value]);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) {
      return;
    }
    onSend(trimmed);
    setValue("");
  };

  const onSubmit = (event) => {
    event.preventDefault();
    submit();
  };

  const onKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };
  const canSubmit = Boolean(value.trim()) && !disabled;

  const placeholder = !hasAgent
    ? "Select an agent to start chatting"
    : isSending
      ? "Wait for the current response to finish..."
      : `Message ${agentName || "the active agent"}...`;

  const helperText = !hasAgent
    ? "Choose an agent to enable chat."
    : isSending
      ? `Running in ${agentName || "the active agent"}.`
      : "Enter to send. Shift+Enter for newline.";
  const showRuntimeControls = hasAgent;
  const orchestrationEnabled = hasAgent && orchestrationAvailable;
  const orchestrationDisabled = disabled || !orchestrationEnabled;
  const isOrchestrated = runtimeMode === "orchestrated";
  const defaultModel = modelOptions.find((item) => item.id === defaultModelId) || null;
  const selectedModel = modelOptions.find((item) => item.id === modelId) || null;
  const displayedModelId = modelId || defaultModelId || "";
  const modelDisabled = isSending || modelsLoading;
  const orchestrationTitle = !hasAgent
    ? "Choose an agent to configure runtime mode."
    : !orchestrationAvailable
      ? "Orchestration not configured."
      : isSending
        ? "Wait for the current response to finish."
        : isOrchestrated
          ? "Running with the orchestrated runtime."
          : "Switch to the orchestrated runtime.";
  const modelTitle = modelsLoading
    ? "Loading available models."
    : selectedModel
      ? `Using ${selectedModel.label}.`
      : defaultModel
        ? `Using the default model: ${defaultModel.label}.`
        : "Use the backend default model.";
  const defaultOptionLabel = defaultModel
    ? "Workspace default"
    : "Backend default";

  return (
    <form className="composer" onSubmit={onSubmit}>
      <div className="composer-input-shell">
        <label className="sr-only" htmlFor="composer-input">Message</label>
        <textarea
          id="composer-input"
          ref={textareaRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
        />
        <div className="composer-actions">
          <div className="composer-meta">
            <span className="composer-hint">{helperText}</span>
            {showRuntimeControls ? (
              <>
                <label
                  className={[
                    "composer-model-select",
                    modelId ? "active" : "",
                    modelDisabled ? "disabled" : "",
                  ].filter(Boolean).join(" ")}
                  title={modelTitle}
                >
                  <span className="composer-model-field">
                    <span className="composer-model-leading" aria-hidden="true">
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
                      value={displayedModelId}
                      disabled={modelDisabled}
                      aria-label="Choose model"
                      onChange={(event) => {
                        const nextValue = event.target.value;
                        onModelIdChange(nextValue === defaultModelId ? "" : nextValue);
                      }}
                    >
                      <option value="">{defaultOptionLabel}</option>
                      {modelOptions.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                    <span className="composer-model-chevron" aria-hidden="true">
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
                  </span>
                </label>
                <label
                  className={[
                    "composer-runtime-toggle",
                    isOrchestrated ? "active" : "",
                    orchestrationDisabled ? "disabled" : "",
                  ].filter(Boolean).join(" ")}
                  title={orchestrationTitle}
                >
                  <span className="composer-runtime-label">Orchestrated</span>
                  <span className="composer-runtime-switch" aria-hidden="true">
                    <span className="composer-runtime-thumb" />
                  </span>
                  <input
                    type="checkbox"
                    checked={isOrchestrated}
                    disabled={orchestrationDisabled}
                    aria-label="Toggle orchestrated runtime"
                    onChange={(event) => {
                      onSetRuntimeMode(event.target.checked ? "orchestrated" : "direct");
                    }}
                  />
                </label>
              </>
            ) : null}
          </div>
          <button
            type="submit"
            className="composer-submit"
            disabled={!canSubmit}
            aria-label={isSending ? "Sending message" : "Send message"}
          >
            {isSending ? (
              <span className="composer-submit-wait" aria-hidden="true">
                ...
              </span>
            ) : (
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path
                  d="M3.5 12.5L12.5 3.5M12.5 3.5H6.25M12.5 3.5V9.75"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.5"
                />
              </svg>
            )}
            <span className="sr-only">{isSending ? "Sending..." : "Send message"}</span>
          </button>
        </div>
      </div>
    </form>
  );
}
