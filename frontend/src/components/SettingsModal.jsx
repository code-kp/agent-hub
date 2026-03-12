import React, { useEffect, useMemo, useRef, useState } from "react";

import { KnowledgeUploadCard } from "./KnowledgeUploadCard";
import { ResponseStreamingCard } from "./ResponseStreamingCard";
import { ThemeToggle } from "./ThemeToggle";
import { UserIdentityCard } from "./UserIdentityCard";

const SETTINGS_TABS = [
  { id: "appearance", label: "Appearance" },
  { id: "responses", label: "Responses" },
  { id: "identity", label: "Identity" },
  { id: "knowledge", label: "Skill upload" },
];

export function SettingsModal({
  isOpen,
  onClose,
  themeMode,
  onThemeModeChange,
  userId,
  onUserIdChange,
  responseStreaming,
  onResponseStreamingChange,
  defaultModelId,
  modelOptions,
  modelsLoading,
  onDefaultModelIdChange,
}) {
  const [activeTab, setActiveTab] = useState("appearance");
  const panelRef = useRef(null);

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    panelRef.current?.focus();

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

  const modeLabel = useMemo(() => (
    themeMode === "system"
      ? "Auto"
      : themeMode.charAt(0).toUpperCase() + themeMode.slice(1)
  ), [themeMode]);
  const renderTabContent = () => {
    if (activeTab === "identity") {
      return (
        <UserIdentityCard
          userId={userId}
          onUserIdChange={onUserIdChange}
        />
      );
    }

    if (activeTab === "knowledge") {
      return <KnowledgeUploadCard userId={userId} />;
    }

    if (activeTab === "responses") {
      return (
        <ResponseStreamingCard
          enabled={responseStreaming}
          onChange={onResponseStreamingChange}
          defaultModelId={defaultModelId}
          modelOptions={modelOptions}
          modelsLoading={modelsLoading}
          onDefaultModelIdChange={onDefaultModelIdChange}
        />
      );
    }

    return (
      <section className="settings-card">
        <div className="settings-card-header">
          <div>
            <h3>Appearance</h3>
            <p>Choose whether the workspace follows the system theme or stays fixed.</p>
          </div>
          <span className="settings-chip">{modeLabel}</span>
        </div>
        <ThemeToggle value={themeMode} onChange={onThemeModeChange} />
      </section>
    );
  };

  return (
    <div className={isOpen ? "settings-modal open" : "settings-modal"} aria-hidden={!isOpen}>
      <button
        type="button"
        className="settings-backdrop"
        onClick={onClose}
        aria-label="Close settings"
      />

      <section className="settings-panel" ref={panelRef} role="dialog" aria-modal="true" tabIndex={-1}>
        <header className="settings-body-header">
          <div>
            <span className="sidebar-label">Workspace</span>
            <h2>Workspace settings</h2>
            <p>Manage appearance, identity, and shared skills in one place without crowding the chat workspace.</p>
          </div>
          <button type="button" className="sidebar-action" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="settings-layout">
          <aside className="settings-nav">
            <div className="settings-nav-header">
              <span className="sidebar-label">Sections</span>
            </div>

            <div className="settings-tabs" role="tablist" aria-label="Settings categories">
              {SETTINGS_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  id={`settings-tab-${tab.id}`}
                  aria-controls={`settings-panel-${tab.id}`}
                  aria-selected={tab.id === activeTab}
                  className={tab.id === activeTab ? "settings-tab active" : "settings-tab"}
                  onClick={() => setActiveTab(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </aside>

          <div
            className="settings-section"
            role="tabpanel"
            id={`settings-panel-${activeTab}`}
            aria-labelledby={`settings-tab-${activeTab}`}
          >
            {renderTabContent()}
          </div>
        </div>
      </section>
    </div>
  );
}
