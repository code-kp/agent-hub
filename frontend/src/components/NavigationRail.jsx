import React from "react";

import { ChatListSidebar } from "./ChatListSidebar";

export function NavigationRail({
  chats,
  activeChatId,
  onNewChat,
  onOpenSettings,
  onSelectChat,
}) {
  return (
    <aside className="navigation-shell card-shell">
      <ChatListSidebar
        chats={chats}
        activeChatId={activeChatId}
        onSelectChat={onSelectChat}
        onNewChat={onNewChat}
        onOpenSettings={onOpenSettings}
      />
    </aside>
  );
}
