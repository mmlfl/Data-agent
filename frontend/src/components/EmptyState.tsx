const EXAMPLE_PROMPTS = [
  "列出数据库中所有表",
  "用户表有多少行？",
  "描述 orders 表的结构",
];

interface EmptyStateProps {
  onSend: (prompt: string) => void;
  disabled?: boolean;
}

export function EmptyState({ onSend, disabled }: EmptyStateProps) {
  return (
    <div className="empty">
      <h2 className="empty__heading">用自然语言查数据</h2>
      <p className="empty__hint">
        描述你想查的内容，助手会自动查表、看结构、执行查询，并把结果整理给你。
      </p>
      <div className="empty__prompts">
        {EXAMPLE_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            className="empty__prompt"
            onClick={() => onSend(prompt)}
            disabled={disabled}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
