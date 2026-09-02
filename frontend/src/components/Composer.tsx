import type { KeyboardEvent } from "react";

interface ComposerProps {
  input: string;
  loading: boolean;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onCancel: () => void;
}

export function Composer({ input, loading, onInputChange, onSend, onCancel }: ComposerProps) {
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <footer className="composer">
      <textarea
        className="composer__input"
        value={input}
        onChange={(e) => onInputChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="输入问题，Enter 发送，Shift+Enter 换行"
        rows={2}
        disabled={loading}
        aria-label="输入问题"
      />
      <div className="composer__actions">
        {loading ? (
          <button type="button" className="composer__btn composer__btn--cancel" onClick={onCancel}>
            取消
          </button>
        ) : (
          <button
            type="button"
            className="composer__btn composer__btn--send"
            onClick={onSend}
            disabled={!input.trim()}
          >
            发送
          </button>
        )}
      </div>
    </footer>
  );
}
