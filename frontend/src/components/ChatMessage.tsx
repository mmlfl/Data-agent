import type { ChatMessage as ChatMessageType } from "../types";
import { MessageContent } from "./MessageContent";
import { ToolPipeline } from "./ToolPipeline";

interface ChatMessageProps {
  message: ChatMessageType;
  isStreaming?: boolean;
}

export function ChatMessage({ message, isStreaming }: ChatMessageProps) {
  const isUser = message.role === "user";
  const showLoading = !isUser && !message.content && !message.error && isStreaming;

  return (
    <div className={`bubble bubble--${message.role}`}>
      <div className="bubble__role">{isUser ? "你" : "助手"}</div>

      {!isUser && message.toolEvents && message.toolEvents.length > 0 && (
        <ToolPipeline events={message.toolEvents} isStreaming={isStreaming} />
      )}

      {showLoading ? (
        <div className="bubble__content bubble__content--loading">正在分析你的问题…</div>
      ) : (
        message.content &&
        (isUser ? (
          <div className="bubble__content">{message.content}</div>
        ) : (
          <MessageContent content={message.content} />
        ))
      )}

      {message.error && (
        <div className="bubble__content bubble__content--error" role="alert">
          {message.error}
        </div>
      )}
    </div>
  );
}
