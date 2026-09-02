import type {
  ChatMessage as ChatMessageType,
  ToolCallRecord,
} from "../types";
import { MessageContent } from "./MessageContent";
import { QueryRunway } from "./QueryRunway";

interface ChatMessageProps {
  message: ChatMessageType;
  calls: ToolCallRecord[];
  onOpenResult: (resultId: string) => void;
}

function statusLabel(message: ChatMessageType): string | null {
  if (message.phase === "summarizing") return "正在核对结果并生成结论…";
  if (message.phase === "streaming") {
    return message.statusText === "thinking"
      ? "正在分析问题…"
      : message.statusText || "正在处理…";
  }
  if (message.phase === "cancelled") return "本次生成已停止";
  return null;
}

export function ChatMessage({
  message,
  calls,
  onOpenResult,
}: ChatMessageProps) {
  const isUser = message.role === "user";
  const status = statusLabel(message);

  if (isUser) {
    return (
      <article className="turn turn--user">
        <div className="turn__identity">你</div>
        <div className="turn__user-copy">{message.content}</div>
      </article>
    );
  }

  return (
    <article className="turn turn--assistant" aria-live="polite">
      <div className="turn__assistant-head">
        <span className="turn__agent-mark" aria-hidden="true">A</span>
        <div>
          <strong>SQL Agent</strong>
          <span>分析过程与结果</span>
        </div>
      </div>

      {calls.length > 0 && <QueryRunway calls={calls} />}

      {message.content && <MessageContent content={message.content} />}

      {message.finalResult && (
        <div className="turn__result-card">
          <span className="turn__result-kicker">Final insight</span>
          <strong>{message.finalResult.title}</strong>
          <p>{message.finalResult.summary}</p>
          <button
            type="button"
            onClick={() =>
              onOpenResult(message.finalResult!.source_tool_call_id)
            }
          >
            在洞察画布中查看
          </button>
        </div>
      )}

      {status && (
        <div className="turn__status">
          {(message.phase === "streaming" ||
            message.phase === "summarizing") && (
            <span className="turn__status-pulse" aria-hidden="true" />
          )}
          {status}
        </div>
      )}

      {message.error && (
        <div className="turn__error" role="alert">
          <strong>请求未完成</strong>
          <span>{message.error}</span>
        </div>
      )}
    </article>
  );
}
