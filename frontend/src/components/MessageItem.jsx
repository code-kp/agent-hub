import React from "react";

import { AnimatedMessageBody } from "./AnimatedMessageBody";
import { ExecutionSteps } from "./ExecutionSteps";
import { TokenUsagePopover } from "./TokenUsagePopover";
import { formatTime, toDateTimeAttr } from "../lib/time";

export function MessageItem({ message }) {
  const isUser = message.role === "user";
  const timestamp = toDateTimeAttr(message.createdAt);
  const assistantLabel = message.agentName || message.agentId || "Assistant";
  const targetLabel = message.targetAgentName || message.targetAgentId || "";
  const showExecution = !isUser && (Boolean(message.thinkingActive) || Boolean((message.thinking || []).length));
  const isLiveExecution = !isUser && Boolean(message.thinkingActive);
  const assistantText = message.text || (!showExecution && message.streaming ? "Working through the request..." : "");

  return (
    <article
      className={isUser ? "message-row row-user" : "message-row row-assistant"}
      data-message-id={message.id}
      data-live-execution={isLiveExecution ? "true" : "false"}
    >
      <div className={isUser ? "message-cluster user-cluster" : "message-cluster assistant-cluster"}>
        <header className="message-topline">
          <div className="message-origin">
            <span className={isUser ? "message-role user-role" : "message-role assistant-role"}>
              {isUser ? "You" : assistantLabel}
            </span>
            {isUser && targetLabel ? <span className="message-target">To {targetLabel}</span> : null}
            {!isUser && message.streaming ? <span className="message-streaming-badge">Live</span> : null}
          </div>
          <div className="message-meta">
            {!isUser ? (
              <TokenUsagePopover usage={message.usage} streaming={Boolean(message.streaming)} />
            ) : null}
            <time dateTime={timestamp}>{formatTime(message.createdAt)}</time>
          </div>
        </header>
        <div
          className={[
            isUser ? "message-card user-message" : "message-card assistant-message",
            !isUser && message.streaming ? "streaming" : "",
          ].filter(Boolean).join(" ")}
        >
          {showExecution ? (
            <div className="execution-focus-anchor" data-execution-anchor="true">
              <ExecutionSteps
                events={message.thinking || []}
                active={Boolean(message.thinkingActive)}
              />
            </div>
          ) : null}
          {isUser || assistantText ? (
            <AnimatedMessageBody
              text={assistantText}
              streaming={!isUser && Boolean(message.streaming)}
            />
          ) : null}
        </div>
      </div>
    </article>
  );
}
