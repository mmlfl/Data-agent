import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { streamChat } from "../api/chat";
import { chatReducer, createInitialChatState } from "../state/chatReducer";
import type { AgentEvent, ChatMessage } from "../types";
import { cancelRun, followRun, getConversations, restoreConversation } from "../api/runs";

interface ConversationSnapshot {
  id: string;
  title: string;
  input: string;
}

function uid() {
  return crypto.randomUUID();
}

export function useChat(conversationId: string) {
  const [state, dispatch] = useReducer(
    chatReducer,
    conversationId,
    createInitialChatState,
  );
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<ConversationSnapshot[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const activeAssistantRef = useRef<string | null>(null);
  const runRef = useRef<string | null>(null);
  const preferredConversation = useRef(localStorage.getItem("data-agent-active-conversation"));
  const [restoring, setRestoring] = useState(true);
  const loading = restoring || state.phase === "streaming" || state.phase === "summarizing";

  const resume = useCallback(async (id: string) => {
    setRestoring(true);
    try {
      const restored = await restoreConversation(id);
      dispatch({ type: "restore", state: restored.state });
      if (restored.activeRun) {
        const controller = new AbortController(); abortRef.current = controller;
        runRef.current = restored.activeRun;
        const assistantId = `answer:${restored.activeRun}`; activeAssistantRef.current = assistantId;
        setRestoring(false);
        await followRun(restored.activeRun, restored.sequence, event => dispatch({ type: "event", assistantId, event, receivedAt: Date.now() }), controller.signal);
      }
    } catch (error) {
      if (activeAssistantRef.current) dispatch({ type: "request_error", assistantId: activeAssistantRef.current,
        message: error instanceof Error ? error.message : "无法恢复运行，请刷新后重试。" });
    } finally { setRestoring(false); }
  }, []);

  useEffect(() => {
    let disposed = false;
    getConversations().then(async ({ conversations }) => {
      if (disposed) return;
      setHistory(conversations.map(item => ({ ...item, input: "" })));
      const preferred = preferredConversation.current;
      const active = conversations.find(item => item.id === preferred) ?? conversations[0];
      if (active) { setHistory(current => current.filter(item => item.id !== active.id)); await resume(active.id); }
    }).catch(() => {}).finally(() => { if (!disposed) setRestoring(false); });
    return () => { disposed = true; };
  }, [resume]);
  useEffect(() => { localStorage.setItem("data-agent-active-conversation", state.conversationId); }, [state.conversationId]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  const switchConversation = useCallback(
    (id?: string) => {
      if (loading || id === state.conversationId) return;
      const target = id ? history.find((item) => item.id === id) : undefined;
      if (id && !target) return;
      abortRef.current?.abort();
      abortRef.current = null;
      activeAssistantRef.current = null;
      const title = state.messages.find(
        (message) => message.role === "user",
      )?.content;
      setHistory((previous) => [
        ...(title ? [{ id: state.conversationId, title, input }] : []),
        ...previous.filter(
          (item) => item.id !== state.conversationId && item.id !== id,
        ),
      ]);
      if (id) { void resume(id); setInput(target?.input ?? ""); return; }
      dispatch({
        type: "restore",
        state: createInitialChatState(uid()),
      });
      setInput(target?.input ?? "");
    },
    [history, input, loading, state, resume],
  );

  const cancel = useCallback(() => {
    if (runRef.current && activeAssistantRef.current) {
      const assistantId = activeAssistantRef.current;
      dispatch({ type: "event", assistantId, event: { protocol_version: "1", type: "status", content: "取消请求已提交，等待当前调用收尾…" }, receivedAt: Date.now() });
      void cancelRun(runRef.current).catch(error => dispatch({ type: "request_error", assistantId, message: String(error) }));
      return;
    }
    abortRef.current?.abort();
    if (activeAssistantRef.current) {
      dispatch({ type: "cancel", assistantId: activeAssistantRef.current });
    }
  }, []);

  const send = useCallback(
    async (textOverride?: string) => {
      const text = (textOverride ?? input).trim();
      if (!text || loading) return;

      setInput("");

      const userMsg: ChatMessage = { id: uid(), role: "user", content: text };
      const assistantId = uid();
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        phase: "streaming",
        statusText: "thinking",
        toolCallIds: [],
        finalResult: null,
        error: null,
      };
      dispatch({
        type: "start_turn",
        userMessage: userMsg,
        assistantMessage: assistantMsg,
      });
      activeAssistantRef.current = assistantId;

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const runId = uid(); runRef.current = runId;
      let sequence = 0;
      const onEvent = (event: AgentEvent) => {
        if (abortRef.current !== controller || controller.signal.aborted) return;
        const next = Number(event.metadata?.sequence ?? 0);
        if (next && next <= sequence) return;
        sequence = next || sequence;
        if (event.metadata?.input_rejected === true) setInput(current => current || text);
        dispatch({ type: "event", assistantId, event, receivedAt: Date.now() });
      };

      try {
        await streamChat({
          message: text,
          conversationId: state.conversationId,
          signal: controller.signal,
          runId, onEvent,
        });
      } catch (e) {
        if (abortRef.current !== controller) return;
        if ((e as Error).name === "AbortError") return;
        try { await followRun(runId, sequence, onEvent, controller.signal); return; } catch { /* Preserve the original diagnostic when recovery is unavailable. */ }
        const msg = (e as Error).message;
        dispatch({
          type: "request_error",
          assistantId,
          message: `请求未完成：${msg}`,
        });
      } finally {
        if (abortRef.current === controller)
          dispatch({ type: "stream_finished", assistantId });
        if (activeAssistantRef.current === assistantId) {
          activeAssistantRef.current = null;
          runRef.current = null;
        }
      }
    },
    [input, loading, state.conversationId],
  );

  const setActiveResult = useCallback((resultId: string) => {
    dispatch({ type: "set_active_result", resultId });
  }, []);

  const activeResult = state.activeResultId
    ? (state.results[state.activeResultId] ?? null)
    : null;

  return {
    ...state,
    activeResult,
    input,
    setInput,
    loading,
    send,
    cancel,
    setActiveResult,
    switchConversation,
    conversations: [
      ...(state.messages.length
        ? [
            {
              id: state.conversationId,
              title:
                state.messages.find((message) => message.role === "user")
                  ?.content ?? "新的分析",
            },
          ]
        : []),
      ...history.map(({ id, title }) => ({ id, title })),
    ],
  };
}
