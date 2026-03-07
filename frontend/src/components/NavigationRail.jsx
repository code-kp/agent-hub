import React from "react";

import { ChatListSidebar } from "./ChatListSidebar";

export function NavigationRail({
  chats,
  activeChatId,
  onNewChat,
  onSelectChat,
  onThemeChange,
  theme,
}) {
  return (
    <aside className="navigation-shell card-shell">
      <ChatListSidebar
        chats={chats}
        activeChatId={activeChatId}
        onSelectChat={onSelectChat}
        onNewChat={onNewChat}
        onThemeChange={onThemeChange}
        theme={theme}
      />
    </aside>
  );
}
