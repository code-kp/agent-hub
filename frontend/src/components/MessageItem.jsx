import React from "react";

import { ExecutionSteps } from "./ExecutionSteps";
import { MarkdownContent } from "./MarkdownContent";

function formatTime(value) {
  if (!value) {
    return "";
  }
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function MessageItem({ message }) {
  const isUser = message.role === "user";
  const timestamp = message.createdAt ? new Date(message.createdAt).toISOString() : undefined;
  const assistantLabel = message.agentName || message.agentId || "Assistant";
  const targetLabel = message.targetAgentName || message.targetAgentId || "";

  return (
    <article className={isUser ? "message-row row-user" : "message-row row-assistant"}>
      <div className={isUser ? "message-cluster user-cluster" : "message-cluster assistant-cluster"}>
        <header className="message-topline">
          <div className="message-origin">
            <span className={isUser ? "message-role user-role" : "message-role assistant-role"}>
              {isUser ? "You" : assistantLabel}
            </span>
            {isUser && targetLabel ? <span className="message-target">To {targetLabel}</span> : null}
            {!isUser && message.streaming ? <span className="message-streaming-badge">Live</span> : null}
          </div>
          <time dateTime={timestamp}>{formatTime(message.createdAt)}</time>
        </header>
        <div className={isUser ? "message-card user-message" : "message-card assistant-message"}>
          <MarkdownContent
            text={message.text || (message.streaming ? "Working through the request..." : "")}
          />
          {!isUser ? (
            <ExecutionSteps
              events={message.thinking || []}
              active={Boolean(message.thinkingActive)}
            />
          ) : null}
        </div>
      </div>
    </article>
  );
}
