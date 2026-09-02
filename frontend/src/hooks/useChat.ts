import { useCallback, useReducer, useRef, useState } from "react";
import { streamChat } from "../api/chat";
import { chatReducer, createInitialChatState } from "../state/chatReducer";
import type { AgentEvent, ChatMessage } from "../types";

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
  const abortRef = useRef<AbortController | null>(null);
  const activeAssistantRef = useRef<string | null>(null);
  const loading = state.phase === "streaming" || state.phase === "summarizing";

  const cancel = useCallback(() => {
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
      abortRef.current = new AbortController();

      try {
        await streamChat({
          message: text,
          conversationId: state.conversationId,
          signal: abortRef.current.signal,
          onEvent: (event: AgentEvent) => {
            dispatch({
              type: "event",
              assistantId,
              event,
              receivedAt: Date.now(),
            });
          },
        });
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        const msg = (e as Error).message;
        dispatch({
          type: "request_error",
          assistantId,
          message: `请求未完成：${msg}。请确认后端已在 8000 端口运行。`,
        });
      } finally {
        dispatch({ type: "stream_finished", assistantId });
        if (activeAssistantRef.current === assistantId) {
          activeAssistantRef.current = null;
        }
      }
    },
    [input, loading, state.conversationId],
  );

  const setActiveResult = useCallback((resultId: string) => {
    dispatch({ type: "set_active_result", resultId });
  }, []);

  const activeResult = state.activeResultId
    ? state.results[state.activeResultId] ?? null
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
  };
}
