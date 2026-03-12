import React from "react";

import { AgentPickerDrawer } from "./components/AgentPickerDrawer";
import { ChatPanel } from "./components/ChatPanel";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { LoadingScreen } from "./components/LoadingScreen";
import { NavigationRail } from "./components/NavigationRail";
import { SettingsModal } from "./components/SettingsModal";
import { fetchModels } from "./api/client";
import {
  DEFAULT_MODEL_ID_STORAGE_KEY,
  LEGACY_MODEL_NAME_STORAGE_KEY,
  RESPONSE_STREAMING_STORAGE_KEY,
  USER_ID_STORAGE_KEY,
  resolveInitialDefaultModelId,
  normalizeResponseStreaming,
  resolveInitialResponseStreaming,
  resolveInitialUserId,
  sanitizeModelId,
  sanitizeUserId,
} from "./lib/preferences";
import { useWorkspaceChat } from "./hooks/useWorkspaceChat";
import { SMART_AGENT_ID } from "./lib/chatWorkspace";
import {
  THEME_MODE_STORAGE_KEY,
  applyTheme,
  resolveInitialThemeMode,
} from "./lib/theme";

const SIDEBAR_WIDTH_STORAGE_KEY = "agent-hub-sidebar-width";
const SIDEBAR_COLLAPSED_STORAGE_KEY = "agent-hub-sidebar-collapsed";
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

function resolveInitialSidebarCollapsed() {
  if (typeof window === "undefined") {
    return false;
  }

  return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "true";
}

export function App() {
  const [themeMode, setThemeMode] = React.useState(resolveInitialThemeMode);
  const [userId, setUserId] = React.useState(resolveInitialUserId);
  const [defaultModelId, setDefaultModelId] = React.useState(resolveInitialDefaultModelId);
  const [chatModelId, setChatModelId] = React.useState("");
  const [availableModels, setAvailableModels] = React.useState([]);
  const [modelsLoading, setModelsLoading] = React.useState(true);
  const [modelCatalogError, setModelCatalogError] = React.useState("");
  const [responseStreaming, setResponseStreaming] = React.useState(resolveInitialResponseStreaming);
  const [isAgentPickerOpen, setIsAgentPickerOpen] = React.useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = React.useState(false);
  const [agentPickerMode, setAgentPickerMode] = React.useState("switch");
  const [sidebarWidth, setSidebarWidth] = React.useState(resolveInitialSidebarWidth);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = React.useState(resolveInitialSidebarCollapsed);
  const [isResizingSidebar, setIsResizingSidebar] = React.useState(false);
  const resizeStateRef = React.useRef(null);
  const effectiveModelId = chatModelId || defaultModelId;
  const {
    activeAgent,
    activeAgentId,
    activeRuntimeMode,
    activeChat,
    activeSessionId,
    agents,
    agentDirectoryLoading,
    chats,
    error,
    filteredTree,
    initialLoadError,
    initialLoadRetrying,
    isSending,
    isRefreshingTitle,
    loading,
    onDeleteChat,
    onNewChat,
    onRefreshTitle,
    onRenameChat,
    onSelectAgent,
    onSelectChat,
    onSetRuntimeMode,
    onSend,
    orchestrationAvailable,
    refreshAgentDirectory,
    retryInitialLoad,
    serviceHealth,
    sessionLoading,
    searchText,
    setSearchText,
  } = useWorkspaceChat(userId, responseStreaming, effectiveModelId);
  const smartAgent = React.useMemo(
    () => agents.find((item) => item.id === SMART_AGENT_ID) || null,
    [agents],
  );

  React.useEffect(() => {
    applyTheme(themeMode);
    window.localStorage.setItem(THEME_MODE_STORAGE_KEY, themeMode);

    if (themeMode !== "system") {
      return undefined;
    }

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = () => {
      applyTheme("system");
    };

    mediaQuery.addEventListener("change", handleChange);
    return () => {
      mediaQuery.removeEventListener("change", handleChange);
    };
  }, [themeMode]);

  React.useEffect(() => {
    window.localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(sidebarWidth));
  }, [sidebarWidth]);

  React.useEffect(() => {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(isSidebarCollapsed));
  }, [isSidebarCollapsed]);

  React.useEffect(() => {
    window.localStorage.setItem(USER_ID_STORAGE_KEY, sanitizeUserId(userId));
  }, [userId]);

  React.useEffect(() => {
    window.localStorage.setItem(
      DEFAULT_MODEL_ID_STORAGE_KEY,
      sanitizeModelId(defaultModelId),
    );
    window.localStorage.removeItem(LEGACY_MODEL_NAME_STORAGE_KEY);
  }, [defaultModelId]);

  React.useEffect(() => {
    let cancelled = false;

    const loadModelCatalog = async () => {
      setModelsLoading(true);

      try {
        const payload = await fetchModels();
        if (cancelled) {
          return;
        }

        const nextModels = Array.isArray(payload.models) ? payload.models : [];
        setAvailableModels(nextModels);
        setModelCatalogError("");
        setDefaultModelId((current) => (
          current && !nextModels.some((item) => item.id === current) ? "" : current
        ));
        setChatModelId((current) => (
          current && !nextModels.some((item) => item.id === current) ? "" : current
        ));
      } catch (err) {
        if (cancelled) {
          return;
        }

        setAvailableModels([]);
        setModelCatalogError(err?.message || "Failed to load the model catalog.");
        setDefaultModelId("");
        setChatModelId("");
      } finally {
        if (!cancelled) {
          setModelsLoading(false);
        }
      }
    };

    void loadModelCatalog();

    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    window.localStorage.setItem(
      RESPONSE_STREAMING_STORAGE_KEY,
      String(normalizeResponseStreaming(responseStreaming)),
    );
  }, [responseStreaming]);

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
    setSearchText("");
    setIsAgentPickerOpen(true);
    void refreshAgentDirectory();
  }, [refreshAgentDirectory, setSearchText]);
  const openAgentPickerForNewChat = React.useCallback(() => {
    setAgentPickerMode("new_chat");
    setSearchText("");
    setIsAgentPickerOpen(true);
    void refreshAgentDirectory();
  }, [refreshAgentDirectory, setSearchText]);
  const closeAgentPicker = React.useCallback(() => {
    setIsAgentPickerOpen(false);
    setSearchText("");
  }, [setSearchText]);
  const openSettings = React.useCallback(() => {
    setIsSettingsOpen(true);
  }, []);
  const closeSettings = React.useCallback(() => {
    setIsSettingsOpen(false);
  }, []);
  const handleUserIdChange = React.useCallback((nextUserId) => {
    setUserId(sanitizeUserId(nextUserId));
  }, []);
  const handleResponseStreamingChange = React.useCallback((nextValue) => {
    setResponseStreaming(normalizeResponseStreaming(nextValue));
  }, []);
  const handleDefaultModelIdChange = React.useCallback((nextValue) => {
    setDefaultModelId(sanitizeModelId(nextValue));
  }, []);
  const handleChatModelIdChange = React.useCallback((nextValue) => {
    setChatModelId(sanitizeModelId(nextValue));
  }, []);
  const handleAgentPickerSelect = React.useCallback((agentId) => {
    if (agentPickerMode === "new_chat") {
      onNewChat(agentId);
    } else {
      onSelectAgent(agentId);
    }

    closeAgentPicker();
  }, [agentPickerMode, closeAgentPicker, onNewChat, onSelectAgent]);
  const handleStartSmartChat = React.useCallback(() => {
    if (!smartAgent) {
      return;
    }
    onNewChat(smartAgent.id);
  }, [onNewChat, smartAgent]);
  const handleUseSmartAgent = React.useCallback(() => {
    if (!smartAgent) {
      return;
    }
    if (activeChat?.id) {
      onSelectAgent(smartAgent.id);
      return;
    }
    onNewChat(smartAgent.id);
  }, [activeChat?.id, onNewChat, onSelectAgent, smartAgent]);

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

  const bannerError = error || modelCatalogError;

  if (loading || initialLoadError) {
    return (
      <LoadingScreen
        isLoading={loading}
        error={initialLoadError}
        isRetrying={initialLoadRetrying}
        healthState={serviceHealth.state}
        healthMessage={serviceHealth.message}
        onRetry={() => {
          void retryInitialLoad({ retry: true });
        }}
      />
    );
  }

  return (
    <main
      className={[
        "app-shell",
        isResizingSidebar ? "resizing" : "",
        isSidebarCollapsed ? "sidebar-collapsed" : "",
      ].filter(Boolean).join(" ")}
      style={{ "--sidebar-width": `${sidebarWidth}px` }}
    >
      <NavigationRail
        activeChatId={activeChat?.id || ""}
        chats={chats}
        onCollapse={() => setIsSidebarCollapsed(true)}
        onDeleteChat={onDeleteChat}
        onNewChat={openAgentPickerForNewChat}
        onStartSmartChat={handleStartSmartChat}
        onOpenSettings={openSettings}
        onRenameChat={onRenameChat}
        onSelectChat={onSelectChat}
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
        {bannerError ? <div className="error-banner">{bannerError}</div> : null}
        <ErrorBoundary
          resetKey={`${activeChat?.id || ""}:${activeChat?.messages?.length || 0}:${activeAgentId}`}
        >
          <ChatPanel
            agentId={activeAgentId}
            agentName={activeAgent?.name || ""}
            agentDescription={activeAgent?.description || ""}
            chatTitle={activeChat?.title || ""}
            sessionId={activeSessionId}
            sessionLoading={sessionLoading}
            sidebarCollapsed={isSidebarCollapsed}
            messages={activeChat?.messages || []}
            isSending={isSending}
            isRefreshingTitle={isRefreshingTitle}
            disabled={!activeAgentId || isSending}
            orchestrationAvailable={orchestrationAvailable}
            defaultModelId={defaultModelId}
            modelId={chatModelId}
            modelOptions={availableModels}
            modelsLoading={modelsLoading}
            runtimeMode={activeRuntimeMode}
            onModelIdChange={handleChatModelIdChange}
            onOpenAgentPicker={openAgentPickerForSwitch}
            onRefreshTitle={onRefreshTitle}
            onSetRuntimeMode={onSetRuntimeMode}
            onUseSmartAgent={handleUseSmartAgent}
            onToggleSidebar={() => setIsSidebarCollapsed((current) => !current)}
            onSend={onSend}
            showSmartAction={Boolean(smartAgent)}
            smartAgentActive={activeAgentId === SMART_AGENT_ID}
          />
        </ErrorBoundary>
      </section>

      <AgentPickerDrawer
        isOpen={isAgentPickerOpen}
        isLoading={agentDirectoryLoading}
        mode={agentPickerMode}
        selectedAgentId={agentPickerMode === "switch" ? activeAgentId : ""}
        smartAgent={smartAgent}
        tree={filteredTree}
        onClose={closeAgentPicker}
        onSelectAgent={handleAgentPickerSelect}
        searchText={searchText}
        onSearchTextChange={setSearchText}
      />
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={closeSettings}
        themeMode={themeMode}
        onThemeModeChange={setThemeMode}
        userId={userId}
        onUserIdChange={handleUserIdChange}
        responseStreaming={responseStreaming}
        onResponseStreamingChange={handleResponseStreamingChange}
        defaultModelId={defaultModelId}
        modelOptions={availableModels}
        modelsLoading={modelsLoading}
        onDefaultModelIdChange={handleDefaultModelIdChange}
      />
    </main>
  );
}
