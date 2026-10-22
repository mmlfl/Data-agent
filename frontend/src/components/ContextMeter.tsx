interface ContextUsage {
  tokens: number;
  windowTokens: number;
}

interface ContextMeterProps {
  usage: ContextUsage | null;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) {
    const v = n / 1_000_000;
    return `${v >= 10 ? v.toFixed(0) : v.toFixed(1).replace(/\.0$/, "")}M`;
  }
  if (n >= 1000) {
    const v = n / 1000;
    return `${v >= 100 ? v.toFixed(0) : v.toFixed(1).replace(/\.0$/, "")}K`;
  }
  return String(n);
}

/** Cursor-like donut showing used / window tokens. */
export function ContextMeter({ usage }: ContextMeterProps) {
  const tokens = usage?.tokens ?? 0;
  const windowTokens = usage?.windowTokens ?? 256_000;
  const ratio = windowTokens > 0 ? Math.min(tokens / windowTokens, 1) : 0;
  const pct = Math.round(ratio * 100);
  const size = 18;
  const stroke = 2.5;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - ratio);

  const tone =
    ratio >= 0.92 ? "critical" : ratio >= 0.75 ? "warn" : ratio > 0 ? "ok" : "idle";

  return (
    <div
      className={`context-meter context-meter--${tone}`}
      title={`上下文约 ${tokens.toLocaleString()} / ${windowTokens.toLocaleString()} tokens（估算值；预留回答空间，超限自动刷新模型上下文并继续）`}
      aria-label={`上下文 ${formatTokens(tokens)} / ${formatTokens(windowTokens)}`}
    >
      <svg
        className="context-meter__ring"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        aria-hidden="true"
      >
        <circle
          className="context-meter__track"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
        />
        <circle
          className="context-meter__progress"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className="context-meter__label">
        <strong>≈{formatTokens(tokens)}</strong>
        <span className="context-meter__sep">/</span>
        {formatTokens(windowTokens)}
        <span className="context-meter__pct">{pct}%</span>
      </span>
    </div>
  );
}

export type { ContextUsage };
