import type { HealthResponse } from "../types";
import type { Theme } from "../hooks/useTheme";
import { Icon } from "./Icon";
import { BrandMark } from "./BrandMark";

interface HeaderProps {
  page: "analysis" | "metadata";
  health: HealthResponse | null;
  healthError: string | null;
  checking: boolean;
  menuOpen: boolean;
  theme: Theme;
  onToggleTheme: () => void;
  onRefresh: () => void;
  onMenu: () => void;
}

export function Header({
  page,
  health,
  healthError,
  checking,
  menuOpen,
  theme,
  onToggleTheme,
  onRefresh,
  onMenu,
}: HeaderProps) {
  return (
    <header className="workspace-header">
      <div className="workspace-header__location">
        <button
          type="button"
          className="icon-button mobile-menu"
          aria-label="打开导航"
          aria-controls="workspace-navigation"
          aria-expanded={menuOpen}
          onClick={onMenu}
        >
          <Icon name="menu" />
        </button>
        <span className="workspace-header__root">
          <Icon name="home" size={17} />
          工作空间
        </span>
        <Icon name="chevron" size={13} />
        <strong>{page === "analysis" ? "分析工作台" : "元数据管理"}</strong>
      </div>
      <div className="workspace-header__actions">
        <button
          type="button"
          className={`connection-pill ${healthError ? "connection-pill--error" : health ? "connection-pill--online" : ""}`}
          onClick={onRefresh}
          disabled={checking}
          title="重新检查服务连接"
        >
          <span className={`status-dot ${checking ? "is-pulsing" : ""}`} />
          {checking
            ? "正在连接"
            : healthError
              ? "服务未连接"
              : health
                ? health.with_db
                  ? "数据源已启用"
                  : "服务已连接"
                : "等待连接"}
          <Icon
            name="refresh"
            size={12}
            className={checking ? "is-spinning" : ""}
          />
        </button>
        <span className="header-divider" />
        <button
          type="button"
          className="icon-button"
          onClick={onToggleTheme}
          aria-label={theme === "dark" ? "切换为浅色主题" : "切换为暗色主题"}
          title={theme === "dark" ? "浅色主题" : "深色主题"}
        >
          <Icon name={theme === "dark" ? "sun" : "moon"} size={18} />
        </button>
        <span className="workspace-avatar" title="本地工作空间">
          <BrandMark size={18} />
        </span>
      </div>
    </header>
  );
}
