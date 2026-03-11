import React, { useCallback, useEffect, useRef, useState } from "react";

import { MessageItem } from "./MessageItem";

const BOTTOM_THRESHOLD_PX = 32;
const NEW_MESSAGE_TOP_OFFSET_PX = 16;

function scrollContainerToBottom(container, behavior = "smooth") {
  container.scrollTo({
    top: container.scrollHeight,
    behavior,
  });
}

function scrollContainerToMessage(container, messageNode, behavior = "smooth") {
  if (!container || !messageNode) {
    return;
  }

  const containerRect = container.getBoundingClientRect();
  const messageRect = messageNode.getBoundingClientRect();
  const nextTop = container.scrollTop + (messageRect.top - containerRect.top) - NEW_MESSAGE_TOP_OFFSET_PX;

  container.scrollTo({
    top: Math.max(0, nextTop),
    behavior,
  });
}

function isScrolledToBottom(container) {
  if (!container) {
    return true;
  }

  const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
  return distanceFromBottom <= BOTTOM_THRESHOLD_PX;
}

function getLatestUserMessageId(messages) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === "user") {
      return messages[index].id || null;
    }
  }

  return null;
}

export function MessageList({ messages, agentName, agentDescription }) {
  const listRef = useRef(null);
  const [showScrollToLatest, setShowScrollToLatest] = useState(false);
  const previousLatestUserMessageIdRef = useRef(getLatestUserMessageId(messages));

  const syncScrollState = useCallback(() => {
    setShowScrollToLatest(!isScrolledToBottom(listRef.current));
  }, []);

  useEffect(() => {
    if (!listRef.current) {
      return undefined;
    }

    const latestUserMessageId = getLatestUserMessageId(messages);
    const previousLatestUserMessageId = previousLatestUserMessageIdRef.current;
    const frameId = window.requestAnimationFrame(() => {
      if (
        latestUserMessageId
        && latestUserMessageId !== previousLatestUserMessageId
        && listRef.current
      ) {
        const messageNode = listRef.current.querySelector(
          `[data-message-id="${latestUserMessageId}"]`,
        );

        if (messageNode) {
          scrollContainerToMessage(listRef.current, messageNode, "smooth");
        }
      }

      syncScrollState();
      previousLatestUserMessageIdRef.current = latestUserMessageId;
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [messages, syncScrollState]);

  if (!messages.length) {
    return (
      <div className="conversation-empty">
        <span className="conversation-empty-badge">{agentName ? "Ready" : "Idle"}</span>
        <h3>{agentName ? `Start with ${agentName}` : "Select an agent to begin"}</h3>
        <p>
          {agentDescription
            || "Switch agents without leaving the thread. Progress updates and responses stay in one shared conversation."}
        </p>
      </div>
    );
  }

  return (
    <div className="message-list-shell">
      <div className="message-list" ref={listRef} onScroll={syncScrollState}>
        {messages.map((message) => <MessageItem key={message.id} message={message} />)}
      </div>
      {showScrollToLatest ? (
        <button
          type="button"
          className="scroll-latest-button"
          onClick={() => {
            if (!listRef.current) {
              return;
            }
            scrollContainerToBottom(listRef.current, "smooth");
          }}
        >
          <span>Scroll to latest</span>
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path
              d="M3.47 6.97a.75.75 0 0 1 1.06 0L8 10.44l3.47-3.47a.75.75 0 1 1 1.06 1.06l-4 4a.75.75 0 0 1-1.06 0l-4-4a.75.75 0 0 1 0-1.06Z"
              fill="currentColor"
            />
          </svg>
        </button>
      ) : null}
    </div>
  );
}
