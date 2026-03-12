import React from "react";

import { ChatListSidebar } from "./ChatListSidebar";

export function NavigationRail({
  chats,
  activeChatId,
  onCollapse,
  onDeleteChat,
  onNewChat,
  onStartSmartChat,
  onOpenSettings,
  onRenameChat,
  onSelectChat,
}) {
  return (
    <aside className="navigation-shell card-shell">
      <ChatListSidebar
        chats={chats}
        activeChatId={activeChatId}
        onCollapse={onCollapse}
        onDeleteChat={onDeleteChat}
        onSelectChat={onSelectChat}
        onNewChat={onNewChat}
        onStartSmartChat={onStartSmartChat}
        onOpenSettings={onOpenSettings}
        onRenameChat={onRenameChat}
      />
    </aside>
  );
}
