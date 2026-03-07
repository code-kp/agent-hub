import React from "react";
import { formatTime, toDateTimeAttr } from "../lib/time";

function getChatStatus(chat) {
  const assistantMessage = [...chat.messages]
    .reverse()
    .find((item) => item.role === "assistant");

  if (!chat.messages.length) {
    return { label: "New", tone: "idle" };
  }

  if (!assistantMessage) {
    return { label: "Draft", tone: "idle" };
  }

  const hasError = (assistantMessage.thinking || []).some(
    (event) => event.state === "error" || event.type === "error",
  );
  if (assistantMessage.thinkingActive || assistantMessage.streaming) {
    return { label: "Running", tone: "running" };
  }
  if (hasError) {
    return { label: "Error", tone: "error" };
  }
  return { label: "Done", tone: "done" };
}

export function ChatListSidebar({
  chats,
  activeChatId,
  onSelectChat,
  onNewChat,
  onOpenSettings,
}) {
  const ordered = [...chats].sort((a, b) => b.updatedAt - a.updatedAt);

  return (
    <section className="chat-sidebar">
      <header className="sidebar-header">
        <div>
          <span className="sidebar-label">Chats</span>
          <h2>Conversations</h2>
        </div>
        <div className="sidebar-header-actions">
          <button type="button" className="sidebar-action" onClick={onNewChat}>
            New
          </button>
        </div>
      </header>

      <div className="chat-sidebar-list">
        {ordered.length ? (
          ordered.map((chat) => {
            const isActive = chat.id === activeChatId;
            const status = getChatStatus(chat);
            return (
              <button
                key={chat.id}
                type="button"
                className={isActive ? "chat-item active" : "chat-item"}
                onClick={() => onSelectChat(chat.id)}
              >
                <div className="chat-item-row">
                  <strong>{chat.title}</strong>
                  <span className={`chat-status ${status.tone}`}>{status.label}</span>
                </div>
                <time className="chat-item-time" dateTime={toDateTimeAttr(chat.updatedAt)}>
                  {formatTime(chat.updatedAt)}
                </time>
              </button>
            );
          })
        ) : (
          <div className="chat-sidebar-empty">Create a chat to start messaging agents.</div>
        )}
      </div>

      <footer className="sidebar-footer">
        <div className="sidebar-footer-copy">
          <span className="sidebar-footer-label">Workspace</span>
          <span className="sidebar-footer-text">Identity, appearance, and knowledge</span>
        </div>
        <button type="button" className="sidebar-action sidebar-settings-button" onClick={onOpenSettings}>
          Open settings
        </button>
      </footer>
    </section>
  );
}
