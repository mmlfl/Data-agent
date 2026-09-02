import type { HealthResponse } from "../types";
import { formatToolList } from "../utils/toolLabels";

interface HeaderProps {
  health: HealthResponse | null;
  healthError: string | null;
}

export function Header({ health, healthError }: HeaderProps) {
  return (
    <header className="header">
      <div>
        <h1 className="header__title">SQL Agent</h1>
        <p className="header__subtitle">用自然语言查询达梦 / MySQL 数据库</p>
      </div>
      <div
        className={`health${healthError ? " health--error" : health?.status === "healthy" ? " health--ok" : ""}`}
        role="status"
      >
        {healthError ? (
          <>
            <span className="health__dot" />
            后端未连接。请启动服务并确认 8000 端口可用。
          </>
        ) : health ? (
          <>
            <span
              className={`health__dot ${health.status === "healthy" ? "health__dot--ok" : ""}`}
            />
            {health.with_db ? health.db_dialect : "未连接数据库"}
            {health.tools.length > 0 && ` · ${formatToolList(health.tools)}`}
          </>
        ) : (
          <>
            <span className="health__dot health__dot--pending" />
            正在连接后端…
          </>
        )}
      </div>
    </header>
  );
}
