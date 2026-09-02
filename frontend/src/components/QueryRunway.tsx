import { useEffect, useMemo, useState } from "react";
import type { ToolCallRecord } from "../types";
import { getToolLabel } from "../utils/toolLabels";
import { ToolDetail } from "./ToolDetail";

function resultSummary(call: ToolCallRecord): string {
  const component = call.component;
  if (call.status === "running") return "处理中";
  if (call.status === "error") return "需要检查";
  if (!component) return "已完成";
  if (component.type === "table_list") return `${component.tables.length} 张候选表`;
  if (component.type === "table_schema") return `${component.columns.length} 个字段`;
  if (component.type === "dataframe") return `${component.row_count} 行`;
  return "结论已生成";
}

export function QueryRunway({ calls }: { calls: ToolCallRecord[] }) {
  const running = calls.find((call) => call.status === "running");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const orderedCalls = useMemo(
    () => [...calls].sort((a, b) => a.startedAt - b.startedAt),
    [calls],
  );

  useEffect(() => {
    if (running) setExpandedId(running.id);
  }, [running?.id]);

  if (orderedCalls.length === 0) return null;

  return (
    <div className="runway" aria-label="查询执行轨迹">
      <div className="runway__eyebrow">
        <span>Query runway</span>
        <span>{orderedCalls.filter((call) => call.status === "success").length}/{orderedCalls.length}</span>
      </div>
      <ol className="runway__list">
        {orderedCalls.map((call) => {
          const expanded = expandedId === call.id;
          return (
            <li
              key={call.id}
              className={`runway__item runway__item--${call.status}`}
            >
              <span className="runway__node" aria-hidden="true" />
              <button
                type="button"
                className="runway__trigger"
                onClick={() => setExpandedId(expanded ? null : call.id)}
                aria-expanded={expanded}
              >
                <span className="runway__step-title">
                  {getToolLabel(call.name)}
                </span>
                <span className="runway__step-meta">
                  {resultSummary(call)}
                  {call.executionTimeMs != null &&
                    ` · ${Math.max(1, Math.round(call.executionTimeMs))}ms`}
                </span>
                <span className="runway__chevron" aria-hidden="true">
                  {expanded ? "−" : "+"}
                </span>
              </button>
              {expanded && <ToolDetail call={call} />}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
