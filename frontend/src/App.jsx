import React from "react";

import { AgentPickerDrawer } from "./components/AgentPickerDrawer";
import { ChatPanel } from "./components/ChatPanel";
import { LoadingScreen } from "./components/LoadingScreen";
import { NavigationRail } from "./components/NavigationRail";
import { useWorkspaceChat } from "./hooks/useWorkspaceChat";
import { THEME_STORAGE_KEY, applyTheme, resolveInitialTheme } from "./lib/theme";

const SIDEBAR_WIDTH_STORAGE_KEY = "agent-hub-sidebar-width";
const DEFAULT_SIDEBAR_WIDTH = 248;
const MIN_SIDEBAR_WIDTH = 220;
const MAX_SIDEBAR_WIDTH = 360;

function clampSidebarWidth(value) {
  return Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, value));
}

function resolveInitialSidebarWidth() {
  if (typeof window === "undefined") {
    return DEFAULT_SIDEBAR_WIDTH;
  }

  const stored = Number.parseInt(window.localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY) || "", 10);
  if (Number.isFinite(stored)) {
    return clampSidebarWidth(stored);
  }

  return DEFAULT_SIDEBAR_WIDTH;
}

export function App() {
  const [isAgentPickerOpen, setIsAgentPickerOpen] = React.useState(false);
  const [agentPickerMode, setAgentPickerMode] = React.useState("switch");
  const [theme, setTheme] = React.useState(resolveInitialTheme);
  const [sidebarWidth, setSidebarWidth] = React.useState(resolveInitialSidebarWidth);
  const [isResizingSidebar, setIsResizingSidebar] = React.useState(false);
  const resizeStateRef = React.useRef(null);
  const {
    activeAgent,
    activeAgentId,
    activeSessionId,
    activeChat,
    chats,
    error,
    filteredTree,
    isSending,
    loading,
    onNewChat,
    onSelectAgent,
    onSelectChat,
    onSend,
    searchText,
    setSearchText,
  } = useWorkspaceChat();

  React.useEffect(() => {
    applyTheme(theme);
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  React.useEffect(() => {
    window.localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(sidebarWidth));
  }, [sidebarWidth]);

  React.useEffect(() => {
    if (!isResizingSidebar) {
      return undefined;
    }

    const handlePointerMove = (event) => {
      const resizeState = resizeStateRef.current;
      if (!resizeState) {
        return;
      }

      const nextWidth = clampSidebarWidth(resizeState.startWidth + event.clientX - resizeState.startX);
      setSidebarWidth(nextWidth);
    };

    const handlePointerUp = () => {
      resizeStateRef.current = null;
      setIsResizingSidebar(false);
    };

    const previousUserSelect = document.body.style.userSelect;
    const previousCursor = document.body.style.cursor;

    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);

    return () => {
      document.body.style.userSelect = previousUserSelect;
      document.body.style.cursor = previousCursor;
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [isResizingSidebar]);

  const openAgentPickerForSwitch = React.useCallback(() => {
    setAgentPickerMode("switch");
    setIsAgentPickerOpen(true);
  }, []);
  const openAgentPickerForNewChat = React.useCallback(() => {
    setAgentPickerMode("new_chat");
    setSearchText("");
    setIsAgentPickerOpen(true);
  }, [setSearchText]);
  const closeAgentPicker = React.useCallback(() => {
    setIsAgentPickerOpen(false);
    setSearchText("");
  }, [setSearchText]);
  const handleAgentPickerSelect = React.useCallback((agentId) => {
    if (agentPickerMode === "new_chat") {
      onNewChat(agentId);
    } else {
      onSelectAgent(agentId);
    }

    closeAgentPicker();
  }, [agentPickerMode, closeAgentPicker, onNewChat, onSelectAgent]);

  const handleSidebarResizeStart = React.useCallback((event) => {
    if (window.innerWidth <= 1100 || event.button !== 0) {
      return;
    }

    event.preventDefault();
    resizeStateRef.current = {
      startWidth: sidebarWidth,
      startX: event.clientX,
    };
    setIsResizingSidebar(true);
  }, [sidebarWidth]);

  const handleSidebarResizeKeyDown = React.useCallback((event) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setSidebarWidth((current) => clampSidebarWidth(current - 16));
      return;
    }

    if (event.key === "ArrowRight") {
      event.preventDefault();
      setSidebarWidth((current) => clampSidebarWidth(current + 16));
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      setSidebarWidth(MIN_SIDEBAR_WIDTH);
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      setSidebarWidth(MAX_SIDEBAR_WIDTH);
    }
  }, []);

  if (loading) {
    return <LoadingScreen />;
  }

  return (
    <main
      className={isResizingSidebar ? "app-shell resizing" : "app-shell"}
      style={{ "--sidebar-width": `${sidebarWidth}px` }}
    >
      <NavigationRail
        activeChatId={activeChat?.id || ""}
        chats={chats}
        onNewChat={openAgentPickerForNewChat}
        onSelectChat={onSelectChat}
        onThemeChange={setTheme}
        theme={theme}
      />
      <div
        className="sidebar-resize-handle"
        role="separator"
        aria-label="Resize sidebar"
        aria-orientation="vertical"
        aria-valuemin={MIN_SIDEBAR_WIDTH}
        aria-valuemax={MAX_SIDEBAR_WIDTH}
        aria-valuenow={sidebarWidth}
        tabIndex={0}
        onDoubleClick={() => setSidebarWidth(DEFAULT_SIDEBAR_WIDTH)}
        onKeyDown={handleSidebarResizeKeyDown}
        onPointerDown={handleSidebarResizeStart}
      />

      <section className="workspace">
        {error ? <div className="error-banner">{error}</div> : null}
        <ChatPanel
          agentId={activeAgentId}
          agentName={activeAgent?.name || ""}
          agentDescription={activeAgent?.description || ""}
          chatTitle={activeChat?.title || ""}
          sessionId={activeSessionId}
          messages={activeChat?.messages || []}
          isSending={isSending}
          disabled={!activeAgentId || isSending}
          onOpenAgentPicker={openAgentPickerForSwitch}
          onSend={onSend}
        />
      </section>

      <AgentPickerDrawer
        isOpen={isAgentPickerOpen}
        mode={agentPickerMode}
        selectedAgentId={agentPickerMode === "switch" ? activeAgentId : ""}
        tree={filteredTree}
        onClose={closeAgentPicker}
        onSelectAgent={handleAgentPickerSelect}
        searchText={searchText}
        onSearchTextChange={setSearchText}
      />
    </main>
  );
}
