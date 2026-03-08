import React, { useEffect, useRef } from "react";

import { MessageItem } from "./MessageItem";

function getActiveExecutionMessage(messages) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === "assistant" && message.thinkingActive) {
      return message;
    }
  }

  return null;
}

function scrollContainerToAnchor(container, anchor, behavior = "smooth") {
  const containerRect = container.getBoundingClientRect();
  const anchorRect = anchor.getBoundingClientRect();
  const focusOffset = Math.min(112, Math.max(32, container.clientHeight * 0.18));
  const nextTop = container.scrollTop + (anchorRect.top - containerRect.top) - focusOffset;

  container.scrollTo({
    top: Math.max(0, nextTop),
    behavior,
  });
}

export function MessageList({ messages, agentName, agentDescription }) {
  const listRef = useRef(null);
  const initialActiveExecution = getActiveExecutionMessage(messages);
  const activeExecutionMessage = getActiveExecutionMessage(messages);
  const previousSnapshotRef = useRef({
    count: messages.length,
    lastId: messages[messages.length - 1]?.id || null,
    lastText: messages[messages.length - 1]?.text || "",
    lastStreaming: Boolean(messages[messages.length - 1]?.streaming),
    activeExecutionId: initialActiveExecution?.id || null,
  });

  useEffect(() => {
    if (!listRef.current) {
      return undefined;
    }

    const lastMessage = messages[messages.length - 1] || null;
    const snapshot = {
      count: messages.length,
      lastId: lastMessage?.id || null,
      lastText: lastMessage?.text || "",
      lastStreaming: Boolean(lastMessage?.streaming),
      activeExecutionId: activeExecutionMessage?.id || null,
    };
    const previousSnapshot = previousSnapshotRef.current;

    if (activeExecutionMessage) {
      if (snapshot.activeExecutionId !== previousSnapshot.activeExecutionId) {
        let settleTimeoutId = 0;
        const frameId = window.requestAnimationFrame(() => {
          if (!listRef.current) {
            return;
          }

          const focusAnchor = (behavior = "smooth") => {
            if (!listRef.current) {
              return;
            }

            const anchor = listRef.current.querySelector(
              `[data-message-id="${activeExecutionMessage.id}"] [data-execution-anchor="true"]`,
            );

            if (anchor) {
              scrollContainerToAnchor(listRef.current, anchor, behavior);
            }
          };

          focusAnchor("smooth");
          settleTimeoutId = window.setTimeout(() => {
            focusAnchor("smooth");
          }, 180);
        });

        previousSnapshotRef.current = snapshot;
        return () => {
          window.cancelAnimationFrame(frameId);
          window.clearTimeout(settleTimeoutId);
        };
      }

      previousSnapshotRef.current = snapshot;
      return undefined;
    }

    if (previousSnapshot.activeExecutionId && !snapshot.activeExecutionId) {
      listRef.current.scrollTo({
        top: listRef.current.scrollHeight,
        behavior: "smooth",
      });

      previousSnapshotRef.current = snapshot;
      return undefined;
    }

    const shouldScroll =
      snapshot.count !== previousSnapshot.count
      || snapshot.lastId !== previousSnapshot.lastId
      || (
        snapshot.lastStreaming
        && snapshot.lastText !== previousSnapshot.lastText
      );

    if (shouldScroll) {
      listRef.current.scrollTo({
        top: listRef.current.scrollHeight,
        behavior: snapshot.count === previousSnapshot.count ? "smooth" : "auto",
      });
    }

    previousSnapshotRef.current = snapshot;
    return undefined;
  }, [messages]);

  useEffect(() => {
    if (!listRef.current || typeof ResizeObserver === "undefined") {
      return undefined;
    }

    const lastMessage = messages[messages.length - 1] || null;
    if (!lastMessage || !lastMessage.streaming) {
      return undefined;
    }

    const container = listRef.current;
    const targetNode = container.querySelector(`[data-message-id="${lastMessage.id}"]`);
    if (!targetNode) {
      return undefined;
    }

    const observer = new ResizeObserver(() => {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: "auto",
      });
    });

    observer.observe(targetNode);
    return () => {
      observer.disconnect();
    };
  }, [messages]);

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
    <div className="message-list" ref={listRef}>
      {messages.map((message) => <MessageItem key={message.id} message={message} />)}
      {activeExecutionMessage ? <div className="message-focus-spacer" aria-hidden="true" /> : null}
    </div>
  );
}
