import React from "react";

import { ChatListSidebar } from "./ChatListSidebar";

export function NavigationRail({
  chats,
  activeChatId,
  onDeleteChat,
  onNewChat,
  onOpenSettings,
  onRenameChat,
  onSelectChat,
}) {
  return (
    <aside className="navigation-shell card-shell">
      <ChatListSidebar
        chats={chats}
        activeChatId={activeChatId}
        onDeleteChat={onDeleteChat}
        onSelectChat={onSelectChat}
        onNewChat={onNewChat}
        onOpenSettings={onOpenSettings}
        onRenameChat={onRenameChat}
      />
    </aside>
  );
}
