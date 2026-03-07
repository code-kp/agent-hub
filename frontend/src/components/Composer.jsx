import React, { useEffect, useRef, useState } from "react";

export function Composer({
  disabled,
  isSending,
  hasAgent,
  agentName,
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
          <span className="composer-hint">{helperText}</span>
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
