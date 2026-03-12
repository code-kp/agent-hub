import React from "react";

import { Composer } from "./Composer";
import { MessageList } from "./MessageList";

function formatSessionId(sessionId) {
  const value = String(sessionId || "").trim();
  if (!value) {
    return "";
  }
  if (value.length <= 22) {
    return value;
  }
  return `${value.slice(0, 8)}...${value.slice(-6)}`;
}

export function ChatPanel({
  agentId,
  agentName,
  agentDescription,
  chatTitle,
  sessionId,
  sessionLoading,
  sidebarCollapsed,
  messages,
  isSending,
  isRefreshingTitle,
  disabled,
  orchestrationAvailable,
  defaultModelId,
  modelId,
  modelOptions,
  modelsLoading,
  runtimeMode,
  onModelIdChange,
  onOpenAgentPicker,
  onRefreshTitle,
  onSetRuntimeMode,
  onToggleSidebar,
  onUseSmartAgent,
  onSend,
  showSmartAction,
  smartAgentActive,
}) {
  const [sessionCopied, setSessionCopied] = React.useState(false);
  const hasActiveAgent = Boolean(agentName || agentId);
  const canRefreshTitle = hasActiveAgent && messages.some((message) => (
    ["user", "assistant"].includes(message?.role)
      && String(message?.text || "").trim()
  ));
  const title = hasActiveAgent
    ? chatTitle || "New conversation"
    : "Start a conversation";
  const sidebarToggleLabel = sidebarCollapsed ? "Show conversations" : "Hide conversations";
  const hasSessionId = Boolean(String(sessionId || "").trim());
  const showSessionChip = hasActiveAgent && (sessionLoading || hasSessionId);
  const sessionValue = sessionLoading
    ? "Loading..."
    : formatSessionId(sessionId);
  const sessionTitle = hasSessionId
    ? (sessionCopied ? "Session id copied" : `Click to copy session id: ${sessionId}`)
    : "Loading session id.";

  React.useEffect(() => {
    if (!sessionCopied) {
      return undefined;
    }

    const timeoutId = window.setTimeout(() => {
      setSessionCopied(false);
    }, 1600);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [sessionCopied]);

  const handleCopySessionId = React.useCallback(async () => {
    if (!hasSessionId) {
      return;
    }

    const value = String(sessionId).trim();

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        const textArea = document.createElement("textarea");
        textArea.value = value;
        textArea.setAttribute("readonly", "");
        textArea.style.position = "absolute";
        textArea.style.left = "-9999px";
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand("copy");
        document.body.removeChild(textArea);
      }
      setSessionCopied(true);
    } catch {
      setSessionCopied(false);
    }
  }, [hasSessionId, sessionId]);

  return (
    <section className="workspace-stage card-shell">
      <header className="workspace-header">
        <div className="workspace-header-copy">
          <div className="workspace-title-row">
            <div className="workspace-title-heading">
              <button
                type="button"
                className={sidebarCollapsed ? "workspace-sidebar-toggle collapsed" : "workspace-sidebar-toggle"}
                onClick={onToggleSidebar}
                aria-label={sidebarToggleLabel}
                title={sidebarToggleLabel}
              >
                <svg viewBox="0 0 16 16" aria-hidden="true">
                  <path
                    d="M2 3.25C2 2.56 2.56 2 3.25 2h9.5c.69 0 1.25.56 1.25 1.25v9.5c0 .69-.56 1.25-1.25 1.25h-9.5C2.56 14 2 13.44 2 12.75v-9.5Zm2.2.25a.3.3 0 0 0-.3.3v8.4c0 .17.13.3.3.3h1.8V3.5H4.2Zm3.1 0v9h5.3a.3.3 0 0 0 .3-.3V3.8a.3.3 0 0 0-.3-.3H7.3Zm4.3 3.15H8.55v-1h3.05v1Zm0 2.45H8.55v-1h3.05v1Z"
                    fill="currentColor"
                  />
                </svg>
              </button>
              <h1>{title}</h1>
              {hasActiveAgent ? (
                <button
                  type="button"
                  className={isRefreshingTitle ? "workspace-title-refresh refreshing" : "workspace-title-refresh"}
                  onClick={onRefreshTitle}
                  disabled={!canRefreshTitle || isSending || isRefreshingTitle}
                  aria-label="Refresh conversation title"
                  title="Regenerate the title from the conversation summary"
                >
                  <svg viewBox="0 0 16 16" aria-hidden="true">
                    <path
                      d="M13.65 3.35A6 6 0 1 0 14 9h-1.8a4.25 4.25 0 1 1-1.04-4.45L9.5 6.2H14V1.7l-1.35 1.65Z"
                      fill="currentColor"
                    />
                  </svg>
                </button>
              ) : null}
            </div>
            <div className="workspace-header-actions">
              {showSessionChip ? (
                <button
                  type="button"
                  className={[
                    "workspace-session-chip",
                    hasSessionId ? "clickable" : "empty",
                    sessionCopied ? "copied" : "",
                  ].filter(Boolean).join(" ")}
                  onClick={() => {
                    void handleCopySessionId();
                  }}
                  disabled={!hasSessionId}
                  title={sessionTitle}
                  aria-label={hasSessionId ? "Copy session id" : "Session id not available yet"}
                >
                  <span className="workspace-session-label">{sessionCopied ? "Copied" : "Session"}</span>
                  <code className="workspace-session-inline-id">{sessionValue}</code>
                </button>
              ) : null}
              {hasActiveAgent ? (
                <div className="workspace-meta">
                  <span>{isSending ? "Streaming" : "Ready"}</span>
                </div>
              ) : (
                <div className="workspace-meta">
                  <span>Choose an agent to begin</span>
                </div>
              )}
            </div>
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
            {showSmartAction ? (
              <button
                type="button"
                className="agent-edit-button smart-agent-button"
                disabled={isSending || smartAgentActive}
                onClick={onUseSmartAgent}
              >
                {smartAgentActive ? "Smart active" : "Use Smart"}
              </button>
            ) : null}
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
            orchestrationAvailable={orchestrationAvailable}
            defaultModelId={defaultModelId}
            modelId={modelId}
            modelOptions={modelOptions}
            modelsLoading={modelsLoading}
            runtimeMode={runtimeMode}
            onModelIdChange={onModelIdChange}
            onSetRuntimeMode={onSetRuntimeMode}
            onSend={onSend}
          />
        </footer>
      </div>
    </section>
  );
}
