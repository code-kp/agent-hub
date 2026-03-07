import React, { useEffect, useRef } from "react";

import { AgentTree } from "./AgentTree";

export function AgentPickerDrawer({
  isOpen,
  mode,
  selectedAgentId,
  tree,
  onClose,
  onSelectAgent,
  searchText,
  onSearchTextChange,
}) {
  const searchInputRef = useRef(null);
  const hasQuery = Boolean(searchText.trim());
  const isNewChatMode = mode === "new_chat";

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    searchInputRef.current?.focus();

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isOpen, onClose]);

  return (
    <div
      className={[
        "agent-drawer",
        isOpen ? "open" : "",
        isNewChatMode ? "new-chat" : "",
      ].filter(Boolean).join(" ")}
      aria-hidden={!isOpen}
    >
      <button
        type="button"
        className="agent-drawer-backdrop"
        onClick={onClose}
        aria-label="Close agent picker"
      />

      <aside className="agent-drawer-panel">
        <header className="agent-drawer-header">
          <div>
            <span className="sidebar-label">Agents</span>
            <h2>{isNewChatMode ? "Start a new chat" : "Browse namespaces"}</h2>
            <p>
              {isNewChatMode
                ? "Pick the agent you want for this new conversation."
                : "Open a namespace first, then pick the agent you want to use in this conversation."}
            </p>
          </div>
          <button
            type="button"
            className="sidebar-action"
            onClick={onClose}
          >
            Close
          </button>
        </header>

        <section className="agent-drawer-search">
          <label className="sr-only" htmlFor="agent-picker-search">Filter namespaces or agents</label>
          <input
            id="agent-picker-search"
            ref={searchInputRef}
            type="text"
            placeholder="Filter namespaces or agents"
            value={searchText}
            onChange={(event) => onSearchTextChange(event.target.value)}
          />
        </section>

        {hasQuery ? (
          <div className="agent-drawer-search-note">Matching branches stay expanded while filtering.</div>
        ) : null}

        <div className="agent-drawer-tree">
          <AgentTree
            tree={tree}
            selectedAgentId={selectedAgentId}
            searchText={searchText}
            onSelectAgent={onSelectAgent}
          />
        </div>
      </aside>
    </div>
  );
}
