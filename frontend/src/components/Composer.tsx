import { useMemo, type KeyboardEvent } from "react";
import { estimateTextTokens } from "../state/contextTokens";
import { ContextMeter, type ContextUsage } from "./ContextMeter";

interface ComposerProps {
  input: string;
  loading: boolean;
  disabled?: boolean;
  disabledReason?: string | null;
  contextUsage?: ContextUsage | null;
  contextNotice?: string | null;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onCancel: () => void;
}

export function Composer({
  input,
  loading,
  disabled = false,
  disabledReason = null,
  contextUsage = null,
  contextNotice = null,
  onInputChange,
  onSend,
  onCancel,
}: ComposerProps) {
  const blocked = disabled && !loading;
  const draftTokens = useMemo(() => estimateTextTokens(input), [input]);
  const inputTooLarge = draftTokens > (contextUsage?.windowTokens ?? 256_000);
  const inputWarning = inputTooLarge
    ? `输入本身约 ${draftTokens.toLocaleString()} tokens，已超过窗口。请缩短或拆成独立任务；原文仍保留在输入框。`
    : input ? `待发送文本约 ${draftTokens.toLocaleString()} tokens；实际可用空间还需扣除系统提示、工具定义和回答预留。` : null;

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (blocked) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!inputTooLarge && !loading) onSend();
    }
  };

  return (
    <footer className="composer">
      <div className="composer__field">
        <textarea
          className="composer__input"
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={
            blocked
              ? disabledReason || "服务暂不可用，请稍后重试"
              : "例如：按月份统计今年订单金额，并标出增长最快的月份"
          }
          rows={2}
          disabled={loading || blocked}
          aria-label="输入数据问题"
        />
        <div className="composer__hint">
          <span>{blocked ? "服务离线" : "只读查询"}</span>
          <div className="composer__hint-right">
            <ContextMeter usage={contextUsage} />
            <span>
              {blocked
                ? disabledReason || "无法连接后端服务"
                : "Enter 发送 · Shift + Enter 换行"}
            </span>
          </div>
        </div>
        {inputWarning ? <div className="composer__notice" role="status">{inputWarning}</div> : null}
        {contextNotice ? (
          <div className="composer__notice" role="status">
            {contextNotice}
          </div>
        ) : null}
      </div>
      {loading ? (
        <button
          type="button"
          className="composer__btn composer__btn--cancel"
          onClick={onCancel}
        >
          停止
        </button>
      ) : (
        <button
          type="button"
          className="composer__btn composer__btn--send"
          onClick={onSend}
          disabled={blocked || inputTooLarge || !input.trim()}
        >
          发送问题 <span aria-hidden="true">↗</span>
        </button>
      )}
    </footer>
  );
}
