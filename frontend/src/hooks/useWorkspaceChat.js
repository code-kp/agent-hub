import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";

import { fetchAgents, streamChat } from "../api/client";
import {
  buildChatTitle,
  createAssistantMessage,
  createChat,
  createThinkingEvent,
  createUserMessage,
  filterTree,
  normalizeAgentTree,
} from "../lib/chatWorkspace";

function buildSessionKey(userId, agentId) {
  return `${userId}::${agentId}`;
}

export function useWorkspaceChat(userId) {
  const [tree, setTree] = useState([]);
  const [agents, setAgents] = useState([]);
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState("");
  const [runningChatIds, setRunningChatIds] = useState(() => new Set());
  const [searchText, setSearchText] = useState("");
  const [loading, setLoading] = useState(true);
  const [agentDirectoryLoading, setAgentDirectoryLoading] = useState(false);
  const [error, setError] = useState("");
  const deferredSearch = useDeferredValue(searchText);

  const applyAgentCatalog = useCallback((data) => {
    const incomingAgents = data.agents || [];
    setTree(normalizeAgentTree(data.tree || []));
    setAgents(incomingAgents);
    return incomingAgents;
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadWorkspace() {
      setLoading(true);
      setError("");

      try {
        const data = await fetchAgents();
        if (cancelled) {
          return;
        }

        const incomingAgents = applyAgentCatalog(data);
        const defaultAgentId = data.default_agent_id || incomingAgents[0]?.id || "";
        const initialChat = defaultAgentId ? createChat(defaultAgentId, incomingAgents, []) : null;

        setChats(initialChat ? [initialChat] : []);
        setActiveChatId(initialChat?.id || "");
      } catch (err) {
        if (!cancelled) {
          setError(err.message || "Failed to load agents.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadWorkspace();

    return () => {
      cancelled = true;
    };
  }, [applyAgentCatalog]);

  const activeChat = useMemo(
    () => chats.find((chat) => chat.id === activeChatId) || null,
    [chats, activeChatId],
  );
  const activeAgentId = activeChat?.agentId || "";
  const activeSessionId = activeChat?.sessionIds?.[buildSessionKey(userId, activeAgentId)] || "";
  const activeAgent = useMemo(
    () => agents.find((item) => item.id === activeAgentId) || null,
    [agents, activeAgentId],
  );
  const isSending = activeChat ? runningChatIds.has(activeChat.id) : false;
  const filteredTree = useMemo(
    () => filterTree(tree, deferredSearch),
    [tree, deferredSearch],
  );

  const updateChat = (chatId, updater) => {
    setChats((prev) => prev.map((chat) => (chat.id === chatId ? updater(chat) : chat)));
  };

  const updateMessage = (chatId, messageId, updater) => {
    setChats((prev) =>
      prev.map((chat) => {
        if (chat.id !== chatId) {
          return chat;
        }

        const index = chat.messages.findIndex((item) => item.id === messageId);
        if (index === -1) {
          return chat;
        }

        const messages = [...chat.messages];
        messages[index] = updater(messages[index]);

        return {
          ...chat,
          messages,
          updatedAt: Date.now(),
        };
      }),
    );
  };

  const appendThinkingEvent = (chatId, messageId, type, payload) => {
    const event = createThinkingEvent(type, payload);
    updateMessage(chatId, messageId, (current) => ({
      ...current,
      thinking: upsertThinkingEvent(current.thinking || [], event),
    }));
  };

  const onSelectAgent = (agentId) => {
    setError("");

    if (!agentId || agentId === activeAgentId) {
      return;
    }

    if (!activeChat) {
      const nextChat = createChat(agentId, agents, chats);
      setChats((prev) => [nextChat, ...prev]);
      setActiveChatId(nextChat.id);
      return;
    }

    updateChat(activeChat.id, (chat) => ({
      ...chat,
      agentId,
      title: chat.messages.length ? chat.title : buildChatTitle(agentId, agents, chats, chat.id),
      updatedAt: Date.now(),
    }));
  };

  const onSelectChat = (chatId) => {
    setActiveChatId(chatId);
    setError("");
  };

  const onNewChat = (agentId = activeAgentId || agents[0]?.id || "") => {
    if (!agentId) {
      return;
    }

    const nextChat = createChat(agentId, agents, chats);
    setChats((prev) => [nextChat, ...prev]);
    setActiveChatId(nextChat.id);
    setError("");
  };

  const refreshAgentDirectory = useCallback(async () => {
    setError("");
    setAgentDirectoryLoading(true);

    try {
      const data = await fetchAgents();
      const incomingAgents = applyAgentCatalog(data);

      if (!activeChatId) {
        const defaultAgentId = data.default_agent_id || incomingAgents[0]?.id || "";
        if (defaultAgentId) {
          const nextChat = createChat(defaultAgentId, incomingAgents, []);
          setChats([nextChat]);
          setActiveChatId(nextChat.id);
        }
      }

      return data;
    } catch (err) {
      setError(err.message || "Failed to refresh agents.");
      throw err;
    } finally {
      setAgentDirectoryLoading(false);
    }
  }, [activeChatId, applyAgentCatalog]);

  const onSend = async (text) => {
    if (!activeChat || !activeAgentId) {
      return;
    }

    const chatId = activeChat.id;
    if (runningChatIds.has(chatId)) {
      return;
    }

    const assistantMessage = createAssistantMessage({
      agentId: activeAgentId,
      agentName: activeAgent?.name || activeAgentId,
    });
    const userMessage = createUserMessage(text, {
      targetAgentId: activeAgentId,
      targetAgentName: activeAgent?.name || activeAgentId,
    });

    updateChat(chatId, (chat) => ({
      ...chat,
      title: chat.messages.some((item) => item.role === "user")
        ? chat.title
        : text.trim().slice(0, 46) || chat.title,
      messages: [...chat.messages, userMessage, assistantMessage],
      updatedAt: Date.now(),
    }));

    setRunningChatIds((prev) => {
      const next = new Set(prev);
      next.add(chatId);
      return next;
    });
    setError("");

    try {
      const result = await streamChat({
        agentId: activeAgentId,
        message: text,
        sessionId: activeSessionId || null,
        userId,
        onEvent: (type, payload = {}) => {
          if (type === "run_started" && payload.session_id) {
            updateChat(chatId, (chat) => ({
              ...chat,
              sessionIds: {
                ...(chat.sessionIds || {}),
                [buildSessionKey(userId, activeAgentId)]: payload.session_id,
              },
              updatedAt: Date.now(),
            }));
          }

          if (type === "thinking_step") {
            appendThinkingEvent(chatId, assistantMessage.id, type, payload);
          }

          if (type === "run_started") {
            updateMessage(chatId, assistantMessage.id, (current) => ({
              ...current,
              thinkingActive: true,
            }));
          }

          if (type === "assistant_delta" && payload.text) {
            updateMessage(chatId, assistantMessage.id, (current) => ({
              ...current,
              text: `${current.text}${payload.text}`,
              streaming: true,
            }));
          }

          if (type === "assistant_message") {
            updateMessage(chatId, assistantMessage.id, (current) => ({
              ...current,
              text: payload.text || current.text,
              streaming: false,
            }));
          }

          if (type === "run_completed") {
            updateMessage(chatId, assistantMessage.id, (current) => ({
              ...current,
              thinkingActive: false,
              streaming: false,
            }));
          }

          if (type === "error") {
            updateMessage(chatId, assistantMessage.id, (current) => ({
              ...current,
              text: current.text || "Run failed before a final assistant message.",
              streaming: false,
              thinkingActive: false,
            }));
          }
        },
      });

      if (result.sessionId) {
        updateChat(chatId, (chat) => ({
          ...chat,
          sessionIds: {
            ...(chat.sessionIds || {}),
            [buildSessionKey(userId, activeAgentId)]: result.sessionId,
          },
          updatedAt: Date.now(),
        }));
      }
    } catch (err) {
      setError(err.message || "Failed to stream response.");
      updateMessage(chatId, assistantMessage.id, (current) => ({
        ...current,
        text: current.text || "Request failed before streaming began.",
        streaming: false,
        thinking: [
          ...(current.thinking || []),
          createThinkingEvent("thinking_step", {
            label: "Could not complete the answer",
            detail: err.message || "Request failed before streaming began.",
            state: "error",
          }),
        ],
        thinkingActive: false,
      }));
    } finally {
      setRunningChatIds((prev) => {
        const next = new Set(prev);
        next.delete(chatId);
        return next;
      });
    }
  };

  return {
    activeAgent,
    activeAgentId,
    activeSessionId,
    activeChat,
    agents,
    agentDirectoryLoading,
    chats,
    error,
    filteredTree,
    isSending,
    loading,
    onNewChat,
    onSelectAgent,
    onSelectChat,
    onSend,
    refreshAgentDirectory,
    searchText,
    setSearchText,
  };
}

function upsertThinkingEvent(events, nextEvent) {
  if (!nextEvent.stepId) {
    return [...events, nextEvent];
  }

  const index = events.findIndex((event) => event.stepId === nextEvent.stepId);
  if (index === -1) {
    return [...events, nextEvent];
  }

  const updated = [...events];
  updated[index] = {
    ...updated[index],
    ...nextEvent,
    id: updated[index].id,
    stepId: updated[index].stepId,
  };
  return updated;
}
