const EXAMPLE_PROMPTS = [
  {
    label: "快速盘点",
    prompt: "列出数据库中所有表，并按用途做简要分类",
  },
  {
    label: "指标查询",
    prompt: "用户表有多少行？请给出结果并说明查询口径",
  },
  {
    label: "结构核对",
    prompt: "描述 orders 表的结构，并指出适合做统计的字段",
  },
];

interface EmptyStateProps {
  onSend: (prompt: string) => void;
  disabled?: boolean;
}

export function EmptyState({ onSend, disabled }: EmptyStateProps) {
  return (
    <div className="empty">
      <div className="empty__signal" aria-hidden="true">
        <span>问</span><i /><span>查</span><i /><span>算</span><i /><span>解</span>
      </div>
      <div>
        <span className="empty__eyebrow">Natural language to evidence</span>
        <h2 className="empty__heading">从问题到可验证的答案</h2>
        <p className="empty__hint">
          描述业务问题。系统会核对表结构、执行只读 SQL，并把结论、图表和原始数据放在同一条证据链上。
        </p>
      </div>
      <div className="empty__prompts">
        {EXAMPLE_PROMPTS.map((item) => (
          <button
            key={item.label}
            type="button"
            className="empty__prompt"
            onClick={() => onSend(item.prompt)}
            disabled={disabled}
          >
            <span>{item.label}</span>
            <strong>{item.prompt}</strong>
          </button>
        ))}
      </div>
    </div>
  );
}
