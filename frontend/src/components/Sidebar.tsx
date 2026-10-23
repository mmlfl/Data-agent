import { useEffect, useRef, useState } from "react";
import type { HealthResponse } from "../types";
import { Icon } from "./Icon";
import { BrandMark } from "./BrandMark";

export interface ConversationLink {
  id: string;
  title: string;
}

interface SidebarProps {
  page: "analysis" | "metadata";
  open: boolean;
  collapsed: boolean;
  onToggleCollapse: () => void;
  busy: boolean;
  health: HealthResponse | null;
  conversations: ConversationLink[];
  activeId: string;
  onNavigate: (page: "analysis" | "metadata") => void;
  onNew: () => void;
  onOpen: (id: string) => void;
  onClose: () => void;
}

export function Sidebar({
  page,
  open,
  collapsed,
  onToggleCollapse,
  busy,
  health,
  conversations,
  activeId,
  onNavigate,
  onNew,
  onOpen,
  onClose,
}: SidebarProps) {
  const [mobile, setMobile] = useState(
    () => window.matchMedia("(max-width: 760px)").matches,
  );
  const sidebarRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 760px)");
    const update = () => setMobile(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!mobile || !open) return;
    const previous = document.activeElement as HTMLElement | null;
    sidebarRef.current
      ?.querySelector<HTMLButtonElement>(".sidebar__close")
      ?.focus();
    return () => previous?.focus();
  }, [mobile, open]);
  return (
    <>
      {open && (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="关闭导航"
          onClick={onClose}
        />
      )}
      <aside
        id="workspace-navigation"
        ref={sidebarRef}
        className={`sidebar ${open ? "sidebar--open" : ""}${collapsed ? " sidebar--compact" : ""}`}
        aria-label="工作空间导航"
        role={mobile ? "dialog" : undefined}
        aria-modal={mobile && open ? true : undefined}
        aria-hidden={mobile && !open ? true : undefined}
        inert={mobile && !open}
        onKeyDown={(event) => {
          if (!mobile || !open || event.key !== "Tab") return;
          const controls = event.currentTarget.querySelectorAll<HTMLElement>(
            "a[href], button:not([disabled])",
          );
          const first = controls[0];
          const last = controls[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }}
      >
        <button
          type="button"
          className="sidebar__close icon-button"
          aria-label="关闭导航"
          onClick={onClose}
        >
          <Icon name="close" size={16} />
        </button>
        <a
          className="workspace-brand"
          aria-label="Data Agent · 返回分析工作台"
          href="#analysis"
          onClick={(e) => {
            e.preventDefault();
            onNavigate("analysis");
          }}
        >
          <span className="workspace-brand__mark">
            <BrandMark size={28} />
          </span>
          <span className="workspace-brand__name">
            data<span>-agent</span>
          </span>
        </a>
        <button
          type="button"
          className="sidebar__collapse"
          onClick={onToggleCollapse}
          aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
          aria-expanded={!collapsed}
          title={collapsed ? "展开侧栏" : "收起侧栏"}
        >
          <Icon name="chevron" size={14} />
        </button>
        <div className="sidebar__workspace">
          <span className="workspace-tile">
            <Icon name="database" size={16} />
          </span>
          <div>
            <strong>我的数据工作空间</strong>
            <span>PERSONAL WORKSPACE</span>
          </div>
          <span className="sidebar__workspace-dot" />
        </div>
        <button
          type="button"
          className="new-analysis"
          aria-label="新建分析"
          title="新建分析"
          onClick={onNew}
          disabled={busy}
        >
          <Icon name="plus" size={17} />
          <span>新建分析</span>
        </button>
        <span className="sidebar__label">工作空间</span>
        <nav className="sidebar__nav">
          <button
            type="button"
            className={page === "analysis" ? "is-active" : ""}
            aria-label="分析工作台"
            title="分析工作台"
            onClick={() => onNavigate("analysis")}
            aria-current={page === "analysis" ? "page" : undefined}
          >
            <Icon name="grid" />
            <span>分析工作台</span>
            {page === "analysis" && <span className="nav-active-dot" />}
          </button>
          <button
            type="button"
            className={page === "metadata" ? "is-active" : ""}
            aria-label="元数据管理"
            title="元数据管理"
            onClick={() => onNavigate("metadata")}
            aria-current={page === "metadata" ? "page" : undefined}
          >
            <Icon name="database" />
            <span>元数据管理</span>
            <span className="nav-count">2</span>
          </button>
        </nav>
        <div className="sidebar__history">
          <span
            className="sidebar__label"
            title="会话在本次打开期间保留，刷新页面后清除"
          >
            最近分析 <Icon name="clock" size={12} />
          </span>
          {conversations.length === 0 ? (
            <div className="sidebar__empty">
              <Icon name="message" size={21} />
              <span>
                从一个问题开始
                <br />
                让数据带来新的发现
              </span>
            </div>
          ) : (
            conversations.map((item) => (
              <button
                type="button"
                key={item.id}
                className={`history-link ${item.id === activeId && page === "analysis" ? "is-active" : ""}`}
                disabled={busy && item.id !== activeId}
                onClick={() => onOpen(item.id)}
                title={item.title}
              >
                <Icon name="message" size={14} />
                <span>{item.title}</span>
              </button>
            ))
          )}
          {conversations.length > 0 && (
            <p className="sidebar__history-note">本次打开期间保留</p>
          )}
        </div>
        <div className="sidebar__bottom">
          <div className="sidebar-tip">
            <span>
              <Icon name="layers" size={16} /> 元数据准备
            </span>
            <p>同步表结构与检索索引，保持分析上下文更新。</p>
            <button type="button" onClick={() => onNavigate("metadata")}>
              <span
                className={
                  health?.with_db && (health.cache_table_count ?? 0) > 0
                    ? "sidebar-tip__ready"
                    : ""
                }
              >
                {health?.with_db && (health.cache_table_count ?? 0) > 0 ? (
                  <>
                    <span className="status-dot" />
                    缓存已就绪
                  </>
                ) : (
                  "管理元数据"
                )}
              </span>
              <Icon name="arrow" size={14} />
            </button>
          </div>
          <div className="sidebar__footer">
            <span className="sidebar__avatar">DA</span>
            <div>
              <strong>本地工作空间</strong>
              <span>
                {health?.with_db
                  ? health.db_dialect.toUpperCase()
                  : "数据分析工作空间"}
              </span>
            </div>
            <small>LOCAL</small>
          </div>
        </div>
      </aside>
    </>
  );
}
