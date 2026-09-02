import type { HealthResponse } from "../types";
import type { Theme } from "../hooks/useTheme";
interface HeaderProps {
  health: HealthResponse | null;
  healthError: string | null;
  theme: Theme;
  onToggleTheme: () => void;
  syncing: boolean;
  syncMessage: string | null;
  onSyncCache: () => void;
}

function cacheLabel(health: HealthResponse): string {
  if (!health.with_db) return "未启用";
  const n = health.cache_table_count ?? 0;
  const status = health.cache_status;
  if (status === "empty" || n === 0) return "缓存为空";
  if (status === "synced" || status === "cached" || status === "ready") {
    return `${n} 张表`;
  }
  if (status) return status;
  return n > 0 ? `${n} 张表` : "待检查";
}

export function Header({
  health,
  healthError,
  theme,
  onToggleTheme,
  syncing,
  syncMessage,
  onSyncCache,
}: HeaderProps) {
  const canSync = !!health?.with_db && !healthError;
  const serviceState = healthError
    ? "不可用"
    : health
      ? "在线"
      : "检查中";
  const databaseState = health
    ? health.with_db
      ? `${health.db_dialect.toUpperCase()} 已启用`
      : "未启用"
    : "—";

  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand__index">SQL / 01</span>
        <div>
          <h1>Insight Workbench</h1>
          <p>自然语言驱动的可验证数据分析</p>
        </div>
      </div>

      <div className="topbar__system" role="status">
        <div className={`system-state${healthError ? " system-state--error" : ""}`}>
          <span className="system-state__label">服务</span>
          <strong>
            <i
              className={`system-state__dot${
                health && !healthError ? " system-state__dot--ok" : ""
              }`}
            />
            {serviceState}
          </strong>
        </div>
        <div className="system-state">
          <span className="system-state__label">数据库</span>
          <strong>{databaseState}</strong>
        </div>
        <div className="system-state">
          <span className="system-state__label">结构缓存</span>
          <strong>{health ? cacheLabel(health) : "—"}</strong>
        </div>
        <div className="system-state system-state--compact">
          <span className="system-state__label">能力</span>
          <strong>{health ? `${health.tools.length} 项` : "—"}</strong>
        </div>
      </div>

      <div className="topbar__actions">
        <button
          type="button"
          className="topbar__button"
          onClick={onToggleTheme}
          aria-label={theme === "dark" ? "切换为浅色主题" : "切换为暗色主题"}
        >
          <span aria-hidden="true">{theme === "dark" ? "☼" : "◐"}</span>
          {theme === "dark" ? "浅色" : "暗色"}
        </button>
        <button
          type="button"
          className="topbar__button topbar__button--primary"
          onClick={onSyncCache}
          disabled={!canSync || syncing}
          title="从数据库重新拉取表结构到本地 SQLite 缓存"
        >
          <span className={syncing ? "sync-icon sync-icon--active" : "sync-icon"} aria-hidden="true">↻</span>
          {syncing ? "同步中" : "同步缓存"}
        </button>
      </div>
      {syncMessage && (
        <div className="topbar__notice" role="status">{syncMessage}</div>
      )}
    </header>
  );
}
