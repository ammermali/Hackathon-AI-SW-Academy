import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { ApiClientError, checkHealth, deleteUserHistory, fetchUserHistory, sendRagQuery } from "../services/api";
import type {
  BackendStatus,
  ChatMessage,
  ConversationSummary,
  HistoryItem,
  RAGResponse,
} from "../types/rag";

function createSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `conv_${crypto.randomUUID().slice(0, 12)}`;
  }
  return `conv_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function historyItemToMessages(item: HistoryItem): ChatMessage[] {
  return [
    {
      id: `hist_u_${item.id}`,
      role: "user",
      content: item.query,
      createdAt: item.created_at,
    },
    {
      id: `hist_a_${item.id}`,
      role: "assistant",
      content: item.answer,
      createdAt: item.created_at,
      sources: item.sources ?? [],
      needsEscalation: item.needs_escalation,
      cached: item.cache_hit,
      processingTimeMs: item.processing_time_ms,
    },
  ];
}

export function groupHistoryBySession(items: HistoryItem[]): ConversationSummary[] {
  const groups = new Map<string, HistoryItem[]>();

  for (const item of items) {
    const sid = item.session_id || "default_session";
    const existing = groups.get(sid);
    if (existing) {
      existing.push(item);
    } else {
      groups.set(sid, [item]);
    }
  }

  const summaries: ConversationSummary[] = [];

  for (const [sessionId, sessionItems] of groups.entries()) {
    // Sort chronologically ascending within a conversation
    const chronological = [...sessionItems].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime() || a.id - b.id
    );
    const firstQuery = chronological[0]?.query ?? "Conversazione";
    const lastCreatedAt = chronological[chronological.length - 1]?.created_at ?? new Date().toISOString();
    const topics = Array.from(
      new Set(chronological.map((i) => i.topic).filter((t): t is string => Boolean(t)))
    );

    summaries.push({
      sessionId,
      title: firstQuery.length > 56 ? `${firstQuery.slice(0, 56).trim()}…` : firstQuery,
      updatedAt: lastCreatedAt,
      turnCount: chronological.length,
      topics,
      messages: chronological.flatMap(historyItemToMessages),
    });
  }

  return summaries.sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
}

function formatError(err: unknown): { code: ApiClientError["code"]; message: string; retryable: boolean } {
  if (err instanceof ApiClientError) {
    return { code: err.code, message: err.message, retryable: err.retryable };
  }
  return {
    code: "UNKNOWN",
    message: "Si è verificato un errore imprevisto durante la richiesta.",
    retryable: true,
  };
}

export interface UseConversationReturn {
  userId: string;
  activeSessionId: string;
  conversations: ConversationSummary[];
  activeMessages: ChatMessage[];
  backendStatus: BackendStatus;
  isLoadingHistory: boolean;
  isSending: boolean;
  isClearingHistory: boolean;
  bannerError: string | null;
  clearBannerError: () => void;
  refreshHealth: () => Promise<void>;
  refreshHistory: () => Promise<void>;
  changeUserId: (nextUserId: string) => void;
  startNewConversation: () => void;
  selectConversation: (sessionId: string) => void;
  sendMessage: (rawQuery: string) => Promise<void>;
  retryMessage: (assistantErrorMsgId: string) => Promise<void>;
  clearAllHistory: () => Promise<void>;
}

export function useConversation(): UseConversationReturn {
  const { user, authContext, contextVersion, switchUser } = useAuth();
  const userId = user.userId;

  const [activeSessionId, setActiveSessionId] = useState<string>(() => createSessionId());
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [sessionDraftMessages, setSessionDraftMessages] = useState<Record<string, ChatMessage[]>>({});
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false);
  const [isSending, setIsSending] = useState<boolean>(false);
  const [isClearingHistory, setIsClearingHistory] = useState<boolean>(false);
  const [bannerError, setBannerError] = useState<string | null>(null);

  const isSendingRef = useRef(false);

  const refreshHealth = useCallback(async () => {
    setBackendStatus("checking");
    try {
      await checkHealth();
      setBackendStatus("online");
    } catch {
      setBackendStatus("offline");
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    setIsLoadingHistory(true);
    try {
      const res = await fetchUserHistory(userId, 200, authContext);
      setHistoryItems(res.items ?? []);
      setBackendStatus("online");
    } catch (err) {
      const formatted = formatError(err);
      if (formatted.code === "CONNECTION_UNAVAILABLE" || formatted.code === "TIMEOUT") {
        setBackendStatus("offline");
      }
      setBannerError(formatted.message);
    } finally {
      setIsLoadingHistory(false);
    }
  }, [authContext, userId]);

  useEffect(() => {
    setBannerError(null);
    setSessionDraftMessages({});
    setActiveSessionId(createSessionId());
    void refreshHealth();
    void refreshHistory();
  }, [contextVersion, refreshHealth, refreshHistory]);

  const conversations = useMemo(() => groupHistoryBySession(historyItems), [historyItems]);

  const activeMessages = useMemo(() => {
    const serverConv = conversations.find((c) => c.sessionId === activeSessionId);
    const serverMessages = serverConv?.messages ?? [];
    const drafts = sessionDraftMessages[activeSessionId] ?? [];
    return [...serverMessages, ...drafts];
  }, [conversations, activeSessionId, sessionDraftMessages]);

  const clearBannerError = useCallback(() => setBannerError(null), []);

  const changeUserId = useCallback(
    (nextUserId: string) => {
      const cleaned = nextUserId.trim();
      if (!cleaned || cleaned === userId) return;
      setBannerError(null);
      setSessionDraftMessages({});
      setActiveSessionId(createSessionId());
      void switchUser(cleaned);
    },
    [switchUser, userId]
  );

  const startNewConversation = useCallback(() => {
    setBannerError(null);
    setActiveSessionId(createSessionId());
  }, []);

  const selectConversation = useCallback((sessionId: string) => {
    setBannerError(null);
    setActiveSessionId(sessionId);
  }, []);

  const appendPersistedTurn = useCallback(
    (targetSessionId: string, query: string, response: RAGResponse) => {
      const nowIso = new Date().toISOString();
      const syntheticId = response.history_id ?? Date.now();
      const newItem: HistoryItem = {
        id: syntheticId,
        user_id: userId,
        session_id: targetSessionId,
        query,
        intent: null,
        topic: response.sources?.[0]?.area ?? null,
        answer: response.answer,
        sources: response.sources ?? [],
        cache_hit: response.cached,
        processing_time_ms: response.processing_time_ms,
        needs_escalation: response.needs_escalation,
        created_at: nowIso,
      };
      setHistoryItems((prev) => [newItem, ...prev.filter((item) => item.id !== syntheticId)]);
    },
    [userId]
  );

  const sendMessage = useCallback(
    async (rawQuery: string) => {
      const trimmed = rawQuery.trim();
      if (!trimmed || trimmed.length < 2 || isSendingRef.current) {
        return;
      }

      isSendingRef.current = true;
      setIsSending(true);
      setBannerError(null);

      const targetSessionId = activeSessionId;
      const tempUserMsgId = `tmp_u_${Date.now()}`;
      const userMsg: ChatMessage = {
        id: tempUserMsgId,
        role: "user",
        content: trimmed,
        createdAt: new Date().toISOString(),
      };

      setSessionDraftMessages((prev) => ({
        ...prev,
        [targetSessionId]: [...(prev[targetSessionId] ?? []), userMsg],
      }));

      try {
        const response = await sendRagQuery(
          {
            query: trimmed,
            user_id: userId,
            session_id: targetSessionId,
          },
          authContext
        );

        setBackendStatus("online");

        // Remove temporary draft user message now that persisted turn replaces it cleanly
        setSessionDraftMessages((prev) => ({
          ...prev,
          [targetSessionId]: (prev[targetSessionId] ?? []).filter((m) => m.id !== tempUserMsgId),
        }));
        appendPersistedTurn(targetSessionId, trimmed, response);
      } catch (err) {
        const formatted = formatError(err);
        if (formatted.code === "CONNECTION_UNAVAILABLE" || formatted.code === "TIMEOUT") {
          setBackendStatus("offline");
        }
        if (formatted.code === "UNAUTHORIZED" || formatted.code === "FORBIDDEN") {
          setBannerError(formatted.message);
        }

        const errorMsg: ChatMessage = {
          id: `err_${Date.now()}`,
          role: "assistant",
          content: "",
          createdAt: new Date().toISOString(),
          error: {
            code: formatted.code,
            message: formatted.message,
            retryable: formatted.retryable,
            originalQuery: trimmed,
          },
        };

        setSessionDraftMessages((prev) => ({
          ...prev,
          [targetSessionId]: [...(prev[targetSessionId] ?? []), errorMsg],
        }));
      } finally {
        isSendingRef.current = false;
        setIsSending(false);
      }
    },
    [activeSessionId, appendPersistedTurn, authContext, userId]
  );

  const retryMessage = useCallback(
    async (assistantErrorMsgId: string) => {
      if (isSendingRef.current) return;
      const targetSessionId = activeSessionId;
      const drafts = sessionDraftMessages[targetSessionId] ?? [];
      const failedIdx = drafts.findIndex((m) => m.id === assistantErrorMsgId && m.error);
      if (failedIdx === -1) return;

      const failedMsg = drafts[failedIdx];
      const queryToRetry = failedMsg.error?.originalQuery;
      if (!queryToRetry) return;

      // Remove failed assistant card and keep the preceding user bubble clean while retrying
      const precedingUserMsg = failedIdx > 0 && drafts[failedIdx - 1]?.role === "user" ? drafts[failedIdx - 1] : null;
      setSessionDraftMessages((prev) => ({
        ...prev,
        [targetSessionId]: (prev[targetSessionId] ?? []).filter(
          (m) => m.id !== assistantErrorMsgId && m.id !== precedingUserMsg?.id
        ),
      }));

      await sendMessage(queryToRetry);
    },
    [activeSessionId, sendMessage, sessionDraftMessages]
  );

  const clearAllHistory = useCallback(async () => {
    setIsClearingHistory(true);
    setBannerError(null);
    try {
      await deleteUserHistory(userId, authContext);
      setHistoryItems([]);
      setSessionDraftMessages({});
      setActiveSessionId(createSessionId());
      setBackendStatus("online");
    } catch (err) {
      const formatted = formatError(err);
      setBannerError(formatted.message);
    } finally {
      setIsClearingHistory(false);
    }
  }, [authContext, userId]);

  return {
    userId,
    activeSessionId,
    conversations,
    activeMessages,
    backendStatus,
    isLoadingHistory,
    isSending,
    isClearingHistory,
    bannerError,
    clearBannerError,
    refreshHealth,
    refreshHistory,
    changeUserId,
    startNewConversation,
    selectConversation,
    sendMessage,
    retryMessage,
    clearAllHistory,
  };
}
