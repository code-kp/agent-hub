import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";

import { fetchAgents, fetchHealth, streamChat } from "../api/client";
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
  const [initialLoadError, setInitialLoadError] = useState("");
  const [initialLoadRetrying, setInitialLoadRetrying] = useState(false);
  const [serviceHealth, setServiceHealth] = useState({
    state: "checking",
    message: "Checking the agent service.",
  });
  const [error, setError] = useState("");
  const deferredSearch = useDeferredValue(searchText);
  const loadRequestRef = useRef(0);

  const applyAgentCatalog = useCallback((data) => {
    const incomingAgents = data.agents || [];
    setTree(normalizeAgentTree(data.tree || []));
    setAgents(incomingAgents);
    return incomingAgents;
  }, []);

  const loadWorkspace = useCallback(async ({ retry = false } = {}) => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;

    setLoading(true);
    setError("");
    setInitialLoadRetrying(retry);

    if (!retry) {
      setInitialLoadError("");
      setServiceHealth({
        state: "checking",
        message: "Checking whether the agent service is reachable.",
      });
    } else {
      setServiceHealth((current) => ({
        state: current.state === "up" ? "checking" : "down",
        message: "Retrying connection to the agent service.",
      }));
    }

    const healthPromise = fetchHealth().then((result) => {
      if (loadRequestRef.current !== requestId) {
        return result;
      }

      setServiceHealth({
        state: result.ok ? "up" : "down",
        message: result.ok
          ? "Agent service is responding."
          : result.message || "The agent service may be down or unresponsive.",
      });

      return result;
    });

    try {
      const data = await fetchAgents();
      if (loadRequestRef.current !== requestId) {
        return;
      }

      const incomingAgents = applyAgentCatalog(data);
      const defaultAgentId = data.default_agent_id || incomingAgents[0]?.id || "";
      const initialChat = defaultAgentId ? createChat(defaultAgentId, incomingAgents, []) : null;

      setChats(initialChat ? [initialChat] : []);
      setActiveChatId(initialChat?.id || "");
      setInitialLoadError("");
      setInitialLoadRetrying(false);
    } catch (err) {
      const health = await healthPromise;
      if (loadRequestRef.current !== requestId) {
        return;
      }

      const message = err.message || "Failed to load agents.";
      setInitialLoadError(message);
      setInitialLoadRetrying(false);
      setServiceHealth({
        state: health?.ok ? "up" : "down",
        message: health?.ok
          ? "Agent service is reachable, but loading the live agent registry did not complete."
          : health?.message || "The agent service may be down or unresponsive.",
      });
    } finally {
      if (loadRequestRef.current === requestId) {
        setInitialLoadRetrying(false);
        setLoading(false);
      }
    }
  }, [applyAgentCatalog]);

  useEffect(() => {
    void loadWorkspace();

    return () => {
      loadRequestRef.current += 1;
    };
  }, [loadWorkspace]);

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
      const health = await fetchHealth();
      const message = health.ok
        ? (err.message || "Failed to refresh agents.")
        : `${err.message || "Failed to refresh agents."} Agent service may be down.`;
      setError(message);
      throw new Error(message);
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
    initialLoadError,
    initialLoadRetrying,
    isSending,
    loading,
    onNewChat,
    onSelectAgent,
    onSelectChat,
    onSend,
    refreshAgentDirectory,
    retryInitialLoad: loadWorkspace,
    searchText,
    serviceHealth,
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
