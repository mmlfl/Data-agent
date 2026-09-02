import { useState } from "react";

export function SqlDisclosure({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);

  const copySql = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <details className="sql-disclosure">
      <summary>
        <span>
          <small>SQL statement</small>
          查看本次只读查询
        </span>
        <span aria-hidden="true">＋</span>
      </summary>
      <div className="sql-disclosure__body">
        <button type="button" onClick={() => void copySql()}>
          {copied ? "已复制" : "复制 SQL"}
        </button>
        <pre>{sql}</pre>
      </div>
    </details>
  );
}
