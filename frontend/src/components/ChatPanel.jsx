import React from "react";

import { Composer } from "./Composer";
import { MessageList } from "./MessageList";

export function ChatPanel({
  agentId,
  agentName,
  agentDescription,
  chatTitle,
  sessionId,
  messages,
  isSending,
  disabled,
  onOpenAgentPicker,
  onSend,
}) {
  const hasActiveAgent = Boolean(agentName || agentId);
  const sessionLabel = sessionId ? "Saved context" : "Fresh context";
  const title = hasActiveAgent
    ? chatTitle || "New conversation"
    : "Start a conversation";

  return (
    <section className="workspace-stage card-shell">
      <header className="workspace-header">
        <div className="workspace-header-copy">
          <div className="workspace-title-row">
            <h1>{title}</h1>
            {hasActiveAgent ? (
              <div className="workspace-meta">
                <span>{isSending ? "Streaming" : "Ready"}</span>
                <span>{sessionLabel}</span>
              </div>
            ) : (
              <div className="workspace-meta">
                <span>Choose an agent to begin</span>
              </div>
            )}
          </div>
          <div className="workspace-agent-inline">
            <span className="workspace-agent-label">Agent</span>
            <strong>{agentName || agentId || "Choose agent"}</strong>
            <button
              type="button"
              className="agent-edit-button"
              disabled={isSending}
              onClick={onOpenAgentPicker}
            >
              {hasActiveAgent ? "Edit" : "Choose"}
            </button>
          </div>
          {agentDescription ? <p className="workspace-agent-description">{agentDescription}</p> : null}
        </div>
      </header>
      <div className="transcript-shell">
        <MessageList
          messages={messages}
          agentName={agentName || agentId}
          agentDescription={agentDescription}
        />
        <footer className="composer-shell">
          <Composer
            disabled={disabled}
            isSending={isSending}
            hasAgent={Boolean(agentName || agentId)}
            agentName={agentName || agentId}
            onSend={onSend}
          />
        </footer>
      </div>
    </section>
  );
}
