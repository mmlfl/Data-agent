import type { KeyboardEvent } from "react";

interface ComposerProps {
  input: string;
  loading: boolean;
  disabled?: boolean;
  disabledReason?: string | null;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onCancel: () => void;
}

export function Composer({
  input,
  loading,
  disabled = false,
  disabledReason = null,
  onInputChange,
  onSend,
  onCancel,
}: ComposerProps) {
  const blocked = disabled && !loading;

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (blocked) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
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
          <span>
            {blocked
              ? disabledReason || "无法连接后端服务"
              : "Enter 发送 · Shift + Enter 换行"}
          </span>
        </div>
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
          disabled={blocked || !input.trim()}
        >
          发送问题 <span aria-hidden="true">↗</span>
        </button>
      )}
    </footer>
  );
}
