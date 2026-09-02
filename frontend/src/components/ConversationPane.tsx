import { useEffect, useMemo, useRef } from "react";
import type { ChatMessage as ChatMessageType, ToolCallRecord } from "../types";
import { ChatMessage } from "./ChatMessage";
import { Composer } from "./Composer";
import { EmptyState } from "./EmptyState";

const NEAR_BOTTOM_PX = 96;

interface ConversationPaneProps {
  messages: ChatMessageType[];
  toolCalls: Record<string, ToolCallRecord>;
  input: string;
  loading: boolean;
  disabled: boolean;
  onInputChange: (value: string) => void;
  onSend: (prompt?: string) => void;
  onCancel: () => void;
  onOpenResult: (resultId: string) => void;
}

export function ConversationPane({
  messages,
  toolCalls,
  input,
  loading,
  disabled,
  onInputChange,
  onSend,
  onCancel,
  onOpenResult,
}: ConversationPaneProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const assistantCount = useMemo(
    () => messages.filter((message) => message.role === "assistant").length,
    [messages],
  );

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      stickToBottomRef.current = distance <= NEAR_BOTTOM_PX;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!stickToBottomRef.current) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, toolCalls, loading]);

  return (
    <section className="conversation-pane" aria-label="分析对话">
      <header className="pane-heading">
        <div>
          <span className="pane-heading__eyebrow">Conversation</span>
          <h2>分析对话</h2>
        </div>
        <span className="pane-heading__meta">
          {assistantCount > 0 ? `${assistantCount} 轮分析` : "等待问题"}
        </span>
      </header>

      <div className="conversation-pane__scroll" ref={scrollRef}>
        {messages.length === 0 ? (
          <EmptyState
            onSend={(prompt) => onSend(prompt)}
            disabled={disabled || loading}
          />
        ) : (
          messages.map((message) => {
            const calls = (message.toolCallIds ?? [])
              .map((id) => toolCalls[id])
              .filter((call): call is ToolCallRecord => Boolean(call));
            return (
              <ChatMessage
                key={message.id}
                message={message}
                calls={calls}
                onOpenResult={onOpenResult}
              />
            );
          })
        )}
        <div ref={bottomRef} />
      </div>

      <Composer
        input={input}
        loading={loading}
        disabled={disabled}
        disabledReason={disabled ? "后端服务不可用，请检查后重试" : null}
        onInputChange={onInputChange}
        onSend={() => onSend()}
        onCancel={onCancel}
      />
    </section>
  );
}
