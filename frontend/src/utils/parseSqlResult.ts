import type { AgentEvent } from "../types";
import type { SqlResultData } from "../types/sqlResult";

export function parseSqlResult(metadata?: Record<string, unknown>): SqlResultData | null {
  if (!metadata) return null;

  const columns = metadata.columns;
  const rows = metadata.rows;
  if (!Array.isArray(columns) || columns.length === 0) return null;
  if (!Array.isArray(rows)) return null;

  const typedColumns = columns.filter((c): c is string => typeof c === "string");
  const typedRows = rows.filter(
    (r): r is Record<string, unknown> => r !== null && typeof r === "object" && !Array.isArray(r),
  );

  return {
    columns: typedColumns,
    rows: typedRows,
    rowCount: typeof metadata.row_count === "number" ? metadata.row_count : typedRows.length,
    sql: typeof metadata.sql === "string" ? metadata.sql : undefined,
    truncated: metadata.truncated === true,
  };
}

export function parseSqlFromEvent(event: AgentEvent): string | null {
  const args = event.metadata?.arguments;
  if (args && typeof args === "object" && !Array.isArray(args)) {
    const sql = (args as Record<string, unknown>).sql;
    if (typeof sql === "string") return sql;
  }
  return null;
}

export function hasTableResult(event: AgentEvent): boolean {
  return event.type === "tool_result" && event.tool_name === "run_sql" && parseSqlResult(event.metadata) !== null;
}
