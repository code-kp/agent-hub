import React, { useEffect, useRef } from "react";

import { MessageItem } from "./MessageItem";

export function MessageList({ messages, agentName, agentDescription }) {
  const listRef = useRef(null);

  useEffect(() => {
    if (!listRef.current) {
      return;
    }
    listRef.current.scrollTop = listRef.current.scrollHeight;
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
    </div>
  );
}
