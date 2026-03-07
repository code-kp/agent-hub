import React from "react";

import { ExecutionSteps } from "./ExecutionSteps";
import { MarkdownContent } from "./MarkdownContent";
import { formatTime, toDateTimeAttr } from "../lib/time";

export function MessageItem({ message }) {
  const isUser = message.role === "user";
  const timestamp = toDateTimeAttr(message.createdAt);
  const assistantLabel = message.agentName || message.agentId || "Assistant";
  const targetLabel = message.targetAgentName || message.targetAgentId || "";
  const showExecution = !isUser && (Boolean(message.thinkingActive) || Boolean((message.thinking || []).length));
  const assistantText = message.text || (!showExecution && message.streaming ? "Working through the request..." : "");

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
          {showExecution ? (
            <ExecutionSteps
              events={message.thinking || []}
              active={Boolean(message.thinkingActive)}
            />
          ) : null}
          {isUser || assistantText ? <MarkdownContent text={assistantText} /> : null}
        </div>
      </div>
    </article>
  );
}
