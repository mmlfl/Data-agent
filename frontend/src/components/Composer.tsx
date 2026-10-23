import { useMemo, type KeyboardEvent, type ReactNode } from "react";
import { estimateTextTokens } from "../state/contextTokens";
import { ContextMeter, type ContextUsage } from "./ContextMeter";
import { Icon } from "./Icon";

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
  variant?: "home" | "conversation";
  toolbarContent?: ReactNode;
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
  variant = "conversation",
  toolbarContent,
}: ComposerProps) {
  const blocked = disabled && !loading;
  const draftTokens = useMemo(() => estimateTextTokens(input), [input]);
  const inputTooLarge = draftTokens > (contextUsage?.windowTokens ?? 256_000);
  const inputWarning = inputTooLarge
    ? "问题内容过长，请缩短文本或拆成几个问题。原文已保留在输入框中。"
    : null;

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (blocked || e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!inputTooLarge && !loading) onSend();
    }
  };

  return (
    <footer className={`composer composer--${variant}`}>
      <div className="composer__field">
        <textarea
          className="composer__input"
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={
            blocked
              ? disabledReason || "服务暂不可用，请稍后重试"
              : variant === "home"
                ? "描述你想了解的问题，例如：今年每个月的订单金额如何变化？"
                : "继续追问，或提出一个新的分析问题…"
          }
          rows={2}
          disabled={loading || blocked}
          aria-label="输入数据问题"
        />
        <div className="composer__toolbar">
          {toolbarContent ? (
            <div className="composer__tools">{toolbarContent}</div>
          ) : (
            <div className="composer__hint">
              <span>
                <Icon name="database" size={12} />
                {blocked ? "服务离线" : "数据库智能分析"}
              </span>
              <div className="composer__hint-right">
                {contextUsage && <ContextMeter usage={contextUsage} />}
                <span>
                  {blocked
                    ? disabledReason || "无法连接后端服务"
                    : "Enter 发送 · Shift + Enter 换行"}
                </span>
              </div>
            </div>
          )}
          {loading ? (
            <button
              type="button"
              className="composer__btn composer__btn--cancel"
              onClick={onCancel}
            >
              <Icon name="stop" size={15} />
              停止生成
            </button>
          ) : (
            <button
              type="button"
              className="composer__btn composer__btn--send"
              onClick={onSend}
              disabled={blocked || inputTooLarge || !input.trim()}
            >
              {variant === "home" && <Icon name="sparkles" size={16} />}
              {variant === "home" ? "开始分析" : "发送"}
              <Icon name="arrow" size={16} />
            </button>
          )}
        </div>
        {inputWarning ? (
          <div className="composer__notice" role="status">
            {inputWarning}
          </div>
        ) : null}
        {contextNotice ? (
          <div className="composer__notice" role="status">
            {contextNotice}
          </div>
        ) : null}
      </div>
    </footer>
  );
}
