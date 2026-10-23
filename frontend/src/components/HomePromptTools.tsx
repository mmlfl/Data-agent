import { useEffect, useId, useRef, useState } from "react";
import type { HealthResponse } from "../types";
import { Icon } from "./Icon";

interface HomePromptToolsProps {
  health: HealthResponse | null;
  onMetadata: () => void;
  onAddTable: (table: string) => void;
  onExample: () => void;
}

export function HomePromptTools({
  health,
  onMetadata,
  onAddTable,
  onExample,
}: HomePromptToolsProps) {
  const [panel, setPanel] = useState<"source" | "table" | null>(null);
  const [table, setTable] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const id = useId();

  useEffect(() => {
    if (!panel) return;
    const outside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setPanel(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPanel(null);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [panel]);

  return (
    <div className="prompt-tools" ref={rootRef}>
      <button
        type="button"
        className="prompt-tool"
        aria-expanded={panel === "source"}
        aria-controls={`${id}-source`}
        onClick={(event) => {
          triggerRef.current = event.currentTarget;
          setPanel(panel === "source" ? null : "source");
        }}
      >
        <Icon name="database" size={15} />
        <span>
          {health?.with_db ? health.db_dialect.toUpperCase() : "当前数据源"}
        </span>
        <Icon name="chevron" size={11} className="turn-down" />
      </button>
      <button
        type="button"
        className="prompt-tool"
        aria-expanded={panel === "table"}
        aria-controls={`${id}-table`}
        onClick={(event) => {
          triggerRef.current = event.currentTarget;
          setPanel(panel === "table" ? null : "table");
        }}
      >
        <Icon name="hash" size={15} />
        <span>添加表</span>
      </button>
      <button
        type="button"
        className="prompt-tool prompt-tool--example"
        onClick={() => {
          setPanel(null);
          onExample();
        }}
      >
        <Icon name="code" size={16} />
        <span>示例问题</span>
      </button>
      {panel === "source" && (
        <section
          className="prompt-popover"
          id={`${id}-source`}
          aria-label="当前数据源"
        >
          <span className="popover-eyebrow">工作空间数据源</span>
          <strong>
            <Icon name="database" size={17} />
            {health?.with_db
              ? `${health.db_dialect.toUpperCase()} 数据库`
              : health
                ? "数据库尚未启用"
                : "服务尚未连接"}
          </strong>
          <p>
            分析使用当前工作空间配置的数据源。你可以在元数据管理中同步表结构与检索索引。
          </p>
          <button
            type="button"
            onClick={() => {
              setPanel(null);
              onMetadata();
            }}
          >
            管理元数据
            <Icon name="arrow" size={14} />
          </button>
        </section>
      )}
      {panel === "table" && (
        <form
          className="prompt-popover"
          id={`${id}-table`}
          aria-label="添加分析表"
          onSubmit={(event) => {
            event.preventDefault();
            if (!table.trim()) return;
            onAddTable(table.trim());
            setTable("");
            setPanel(null);
          }}
        >
          <label htmlFor={`${id}-name`}>指定要分析的表</label>
          <p>将表名加入问题，让分析范围更明确。</p>
          <input
            id={`${id}-name`}
            value={table}
            onChange={(event) => setTable(event.target.value)}
            placeholder="例如：public.orders"
            maxLength={128}
            required
            autoFocus
            autoComplete="off"
          />
          <button type="submit" disabled={!table.trim()}>
            加入问题
            <Icon name="plus" size={14} />
          </button>
        </form>
      )}
    </div>
  );
}
