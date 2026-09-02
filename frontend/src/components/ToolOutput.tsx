import type { AgentEvent } from "../types";
import { getToolLabel } from "../utils/toolLabels";
import { hasTableResult, parseSqlFromEvent, parseSqlResult } from "../utils/parseSqlResult";
import { QueryResultTable } from "./QueryResultTable";

function isSqlContent(content: string | null | undefined): boolean {
  if (!content) return false;
  const upper = content.trim().toUpperCase();
  return (
    upper.startsWith("SELECT") ||
    upper.startsWith("INSERT") ||
    upper.startsWith("UPDATE") ||
    upper.startsWith("DELETE") ||
    upper.startsWith("CREATE") ||
    upper.startsWith("DROP")
  );
}

interface ToolOutputProps {
  events: AgentEvent[];
}

export function ToolOutput({ events }: ToolOutputProps) {
  if (events.length === 0) return null;

  return (
    <div className="tool-output">
      {events.map((ev, i) => {
        const label = ev.tool_name ? getToolLabel(ev.tool_name) : "";
        const tableData = hasTableResult(ev) ? parseSqlResult(ev.metadata) : null;
        const sqlFromArgs = parseSqlFromEvent(ev);

        if (tableData) {
          return (
            <div key={i} className="tool-output__panel tool-output__panel--table">
              <div className="tool-output__header">
                <span className="tool-output__badge tool-output__badge--result">结果</span>
                {label}
              </div>
              <QueryResultTable data={tableData} />
            </div>
          );
        }

        if (ev.type === "tool_start" && sqlFromArgs) {
          return (
            <div key={i} className="tool-output__panel">
              <div className="tool-output__header">
                <span className="tool-output__badge tool-output__badge--start">执行中</span>
                {label}
              </div>
              <pre className="tool-output__body tool-output__body--sql">{sqlFromArgs}</pre>
            </div>
          );
        }

        const body = ev.content ?? JSON.stringify(ev.metadata, null, 2);
        const isSql = ev.tool_name === "run_sql" || isSqlContent(ev.content);

        return (
          <div key={i} className="tool-output__panel">
            <div className="tool-output__header">
              <span
                className={`tool-output__badge tool-output__badge--${
                  ev.type === "tool_start" ? "start" : "result"
                }`}
              >
                {ev.type === "tool_start" ? "执行中" : "结果"}
              </span>
              {label}
            </div>
            <pre className={`tool-output__body${isSql ? " tool-output__body--sql" : ""}`}>
              {body}
            </pre>
          </div>
        );
      })}
    </div>
  );
}
