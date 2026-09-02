import { useCallback, useRef, useState } from "react";
import { streamChat } from "../api/chat";
import type { AgentEvent, ChatMessage } from "../types";

function uid() {
  return crypto.randomUUID();
}

export function useChat(conversationId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setLoading(false);
  }, []);

  const send = useCallback(
    async (textOverride?: string) => {
      const text = (textOverride ?? input).trim();
      if (!text || loading) return;

      setInput("");
      setLoading(true);

      const userMsg: ChatMessage = { id: uid(), role: "user", content: text };
      const assistantId = uid();
      setMessages((prev) => [
        ...prev,
        userMsg,
        { id: assistantId, role: "assistant", content: "", toolEvents: [], error: null },
      ]);

      abortRef.current?.abort();
      abortRef.current = new AbortController();

      try {
        await streamChat({
          message: text,
          conversationId,
          signal: abortRef.current.signal,
          onEvent: (event: AgentEvent) => {
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantId) return m;
                const toolEvents = [...(m.toolEvents ?? [])];
                if (
                  event.type === "tool_start" ||
                  event.type === "tool_result" ||
                  event.type === "status"
                ) {
                  toolEvents.push(event);
                }
                let content = m.content;
                let error = m.error ?? null;
                if (event.type === "text_delta" && event.content) {
                  content += event.content;
                } else if (event.type === "text" && event.content) {
                  content = event.content;
                } else if (event.type === "error" && event.content) {
                  error = event.content;
                }
                return { ...m, content, toolEvents, error };
              }),
            );
          },
        });
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        const msg = (e as Error).message;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  error:
                    m.error ??
                    `请求未完成：${msg}。请确认后端已在 8000 端口运行。`,
                }
              : m,
          ),
        );
      } finally {
        setLoading(false);
      }
    },
    [input, loading, conversationId],
  );

  return { messages, input, setInput, loading, send, cancel };
}
