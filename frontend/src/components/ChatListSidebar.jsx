import React from "react";
import { createPortal } from "react-dom";
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
  onCollapse,
  onDeleteChat,
  onSelectChat,
  onNewChat,
  onStartSmartChat,
  onOpenSettings,
  onRenameChat,
}) {
  const [menuChatId, setMenuChatId] = React.useState("");
  const [dialogState, setDialogState] = React.useState({
    type: "",
    chatId: "",
    title: "",
  });
  const [renameValue, setRenameValue] = React.useState("");
  const menuRef = React.useRef(null);
  const ordered = [...chats].sort((a, b) => b.updatedAt - a.updatedAt);

  const closeDialog = React.useCallback(() => {
    setDialogState({ type: "", chatId: "", title: "" });
    setRenameValue("");
  }, []);

  React.useEffect(() => {
    if (!menuChatId) {
      return undefined;
    }

    const handlePointerDown = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuChatId("");
      }
    };

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setMenuChatId("");
      }
    };

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuChatId]);

  React.useEffect(() => {
    if (!dialogState.type) {
      return undefined;
    }

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        closeDialog();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [closeDialog, dialogState.type]);

  const openRenameDialog = React.useCallback((chat) => {
    setMenuChatId("");
    setDialogState({
      type: "rename",
      chatId: chat.id,
      title: chat.title,
    });
    setRenameValue(chat.title);
  }, []);

  const openDeleteDialog = React.useCallback((chat) => {
    setMenuChatId("");
    setDialogState({
      type: "delete",
      chatId: chat.id,
      title: chat.title,
    });
    setRenameValue("");
  }, []);

  const submitRename = React.useCallback((event) => {
    event.preventDefault();
    if (!dialogState.chatId) {
      return;
    }
    onRenameChat(dialogState.chatId, renameValue);
    closeDialog();
  }, [closeDialog, dialogState.chatId, onRenameChat, renameValue]);

  const confirmDelete = React.useCallback(() => {
    if (!dialogState.chatId) {
      return;
    }
    onDeleteChat(dialogState.chatId);
    closeDialog();
  }, [closeDialog, dialogState.chatId, onDeleteChat]);

  return (
    <>
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
            <button type="button" className="sidebar-action sidebar-smart-button" onClick={onStartSmartChat}>
              Smart
            </button>
            <button
              type="button"
              className="sidebar-action sidebar-collapse-button"
              onClick={onCollapse}
              aria-label="Collapse conversations pane"
              title="Collapse conversations pane"
            >
              Hide
            </button>
          </div>
        </header>

        <div className="chat-sidebar-list">
          {ordered.length ? (
            ordered.map((chat) => {
              const isActive = chat.id === activeChatId;
              const status = getChatStatus(chat);
              const canDelete = status.tone !== "running";
              const isMenuOpen = menuChatId === chat.id;
              return (
                <div
                  key={chat.id}
                  className={isActive ? "chat-item-shell active" : "chat-item-shell"}
                >
                  <button
                    type="button"
                    className={isActive ? "chat-item active" : "chat-item"}
                    onClick={() => {
                      setMenuChatId("");
                      onSelectChat(chat.id);
                    }}
                  >
                    <div className="chat-item-row">
                      <strong>{chat.title}</strong>
                      <span className={`chat-status ${status.tone}`}>{status.label}</span>
                    </div>
                    <time className="chat-item-time" dateTime={toDateTimeAttr(chat.updatedAt)}>
                      {formatTime(chat.updatedAt)}
                    </time>
                  </button>
                  <div
                    ref={isMenuOpen ? menuRef : null}
                    className={isMenuOpen ? "chat-item-menu-shell open" : "chat-item-menu-shell"}
                  >
                    <button
                      type="button"
                      className="chat-menu-trigger"
                      onClick={(event) => {
                        event.stopPropagation();
                        setMenuChatId((current) => (current === chat.id ? "" : chat.id));
                      }}
                      aria-label={`More actions for ${chat.title}`}
                      aria-haspopup="menu"
                      aria-expanded={isMenuOpen}
                    >
                      <svg viewBox="0 0 16 16" aria-hidden="true">
                        <path
                          d="M8 3.25a1.25 1.25 0 1 0 0 2.5 1.25 1.25 0 0 0 0-2.5Zm0 3.5a1.25 1.25 0 1 0 0 2.5 1.25 1.25 0 0 0 0-2.5Zm0 3.5a1.25 1.25 0 1 0 0 2.5 1.25 1.25 0 0 0 0-2.5Z"
                          fill="currentColor"
                        />
                      </svg>
                    </button>
                    {isMenuOpen ? (
                      <div className="chat-item-menu" role="menu" aria-label={`Actions for ${chat.title}`}>
                        <button
                          type="button"
                          className="chat-item-menu-action"
                          role="menuitem"
                          onClick={(event) => {
                            event.stopPropagation();
                            openRenameDialog(chat);
                          }}
                        >
                          Rename
                        </button>
                        <button
                          type="button"
                          className="chat-item-menu-action danger"
                          role="menuitem"
                          disabled={!canDelete}
                          onClick={(event) => {
                            event.stopPropagation();
                            if (!canDelete) {
                              return;
                            }
                            openDeleteDialog(chat);
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })
          ) : (
            <div className="chat-sidebar-empty">Start with Smart or choose any agent for your first conversation.</div>
          )}
        </div>

        <footer className="sidebar-footer">
          <div className="sidebar-footer-copy">
            <span className="sidebar-footer-label">Workspace</span>
            <span className="sidebar-footer-text">Identity, appearance, and skills</span>
          </div>
          <button type="button" className="sidebar-action sidebar-settings-button" onClick={onOpenSettings}>
            Open settings
          </button>
        </footer>
      </section>

      <ConversationActionDialog
        dialogState={dialogState}
        renameValue={renameValue}
        onClose={closeDialog}
        onConfirmDelete={confirmDelete}
        onRenameValueChange={setRenameValue}
        onSubmitRename={submitRename}
      />
    </>
  );
}

function ConversationActionDialog({
  dialogState,
  renameValue,
  onClose,
  onConfirmDelete,
  onRenameValueChange,
  onSubmitRename,
}) {
  const isOpen = Boolean(dialogState.type);
  const inputRef = React.useRef(null);

  React.useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    const frameId = window.requestAnimationFrame(() => {
      if (dialogState.type === "rename") {
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [dialogState.type, isOpen]);

  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <div className={isOpen ? "conversation-dialog open" : "conversation-dialog"} aria-hidden={!isOpen}>
      <button
        type="button"
        className="conversation-dialog-backdrop"
        onClick={onClose}
        aria-label="Close conversation action dialog"
      />

      <section className="conversation-dialog-panel" role="dialog" aria-modal="true" aria-labelledby="conversation-dialog-title">
        {dialogState.type === "rename" ? (
          <form className="conversation-dialog-card" onSubmit={onSubmitRename}>
            <div className="conversation-dialog-copy">
              <span className="sidebar-label">Rename</span>
              <h3 id="conversation-dialog-title">Rename conversation</h3>
              <p>Choose a title that will stay with this chat instead of the generated one.</p>
            </div>

            <label className="conversation-dialog-field" htmlFor="conversation-rename-input">
              <span>Title</span>
              <input
                id="conversation-rename-input"
                ref={inputRef}
                type="text"
                value={renameValue}
                onChange={(event) => onRenameValueChange(event.target.value)}
                maxLength={120}
              />
            </label>

            <div className="conversation-dialog-actions">
              <button type="button" className="conversation-dialog-button subtle" onClick={onClose}>
                Cancel
              </button>
              <button
                type="submit"
                className="conversation-dialog-button primary"
                disabled={!String(renameValue || "").trim()}
              >
                Save
              </button>
            </div>
          </form>
        ) : null}

        {dialogState.type === "delete" ? (
          <div className="conversation-dialog-card">
            <div className="conversation-dialog-copy">
              <span className="sidebar-label">Delete</span>
              <h3 id="conversation-dialog-title">Delete conversation?</h3>
              <p>
                <strong>{dialogState.title}</strong> will be removed from this workspace for the current user.
              </p>
            </div>

            <div className="conversation-dialog-actions">
              <button type="button" className="conversation-dialog-button subtle" onClick={onClose}>
                Cancel
              </button>
              <button type="button" className="conversation-dialog-button danger" onClick={onConfirmDelete}>
                Delete
              </button>
            </div>
          </div>
        ) : null}
      </section>
    </div>,
    document.body,
  );
}
