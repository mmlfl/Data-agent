"""run_sql tool — readonly SQL execution via SqlRunnerPool."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Type

import pandas as pd

from sql_agent.capabilities.sql_runner import RunSqlToolArgs
from sql_agent.core.tool.base import Tool
from sql_agent.core.tool.models import ToolContext, ToolResult
from sql_agent.integrations.db.sql_runner_pool import SqlRunnerPool
from sql_agent.integrations.db.sql_validate import validate_sql

MAX_LLM_ROWS = 50
MAX_FRONTEND_ROWS = 500


def normalize_cell(value: Any) -> Any:
    """Convert DB values to JSON-serializable types."""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def format_sql_result(
    columns: list, rows: list, max_rows: int | None = MAX_LLM_ROWS
) -> str:
    """Format SQL result for the LLM."""
    result = f"返回 {len(rows)} 行 | 列: {', '.join(columns)}\n"
    display_rows = rows if max_rows is None else rows[:max_rows]
    for row in display_rows:
        vals = []
        for v in row:
            if v is None:
                vals.append("NULL")
            elif hasattr(v, "isoformat"):
                vals.append(v.isoformat())
            else:
                sv = str(v)
                if len(sv) > 80:
                    sv = sv[:77] + "..."
                vals.append(sv)
        result += " | ".join(vals) + "\n"
    if max_rows is not None and len(rows) > max_rows:
        result += f"... 还有 {len(rows) - max_rows} 行 (共 {len(rows)} 行)"
    return result


def build_result_metadata(columns: list[str], rows: list[tuple], sql: str) -> dict[str, Any]:
    """Build structured metadata for frontend table rendering via pandas."""
    normalized = [[normalize_cell(v) for v in row] for row in rows]
    df = pd.DataFrame(normalized, columns=columns)
    display_df = df.head(MAX_FRONTEND_ROWS)
    records = display_df.where(display_df.notnull(), None).to_dict(orient="records")

    return {
        "row_count": len(rows),
        "columns": columns,
        "rows": records,
        "sql": sql,
        "truncated": len(rows) > MAX_FRONTEND_ROWS,
    }


class RunSqlTool(Tool[RunSqlToolArgs]):
    """Execute read-only SQL using an injected SqlRunnerPool."""

    def __init__(self, pool: SqlRunnerPool) -> None:
        self._pool = pool

    @property
    def name(self) -> str:
        return "run_sql"

    @property
    def description(self) -> str:
        return (
            "在数据库执行只读 SELECT 查询并返回结果。"
            "只能执行 SELECT，禁止 INSERT/UPDATE/DELETE/DDL。"
            "达梦语法用 ROWNUM 限行（不支持 LIMIT）；MySQL 用 LIMIT。"
            "写 SQL 前应先 describe_table 确认字段。"
        )

    def get_args_schema(self) -> Type[RunSqlToolArgs]:
        return RunSqlToolArgs

    async def execute(self, context: ToolContext, args: RunSqlToolArgs) -> ToolResult:
        # 与 sql-agent tools.run_sql 一致：先校验，再进连接池
        if not validate_sql(args.sql):
            msg = "不安全的sql语句，拒绝执行"
            return ToolResult(success=False, result_for_llm=msg, error=msg)

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                with self._pool.borrow() as runner:
                    columns, rows = runner.execute_readonly(args.sql)
                    text = format_sql_result(columns, rows)
                    metadata = build_result_metadata(columns, rows, args.sql)
                    return ToolResult(
                        success=True,
                        result_for_llm=text,
                        metadata=metadata,
                    )
            except PermissionError as e:
                msg = str(e) or "不安全的sql语句，拒绝执行"
                return ToolResult(success=False, result_for_llm=msg, error=msg)
            except Exception as e:
                last_error = e
                if attempt == 0:
                    continue
        msg = f"SQL 执行失败（已重试）: {last_error}"
        return ToolResult(success=False, result_for_llm=msg, error=msg)


# Backward-compatible alias
RunSqlArgs = RunSqlToolArgs
