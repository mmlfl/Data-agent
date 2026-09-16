"""run_sql tool — readonly SQL execution via SqlRunnerPool."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, datetime
from decimal import Decimal
from numbers import Number
from typing import Any, Type

from sql_agent.capabilities.sql_runner import RunSqlToolArgs, SqlExecutionResult
from sql_agent.components import DataColumn, DataFrameComponent
from sql_agent.core.tool.base import Tool
from sql_agent.core.tool.models import ToolContext, ToolResult
from sql_agent.integrations.db.sql_runner_pool import SqlRunnerPool
from sql_agent.integrations.db.sql_validate import validate_sql

MAX_LLM_ROWS = 20
MAX_FRONTEND_ROWS = 500
logger = logging.getLogger(__name__)


def normalize_cell(value: Any) -> Any:
    """Convert DB values to JSON-serializable types."""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return float(value) if value % 1 else int(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Number):
        numeric = float(value)
        return int(numeric) if numeric.is_integer() else numeric
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): normalize_cell(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [normalize_cell(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def format_sql_result(
    columns: list,
    rows: list,
    max_rows: int | None = MAX_LLM_ROWS,
    *,
    truncated: bool = False,
    ui_row_count: int | None = None,
) -> str:
    """Format a compact sample for the LLM; full rows go to ui_component."""
    total = len(rows)
    qualifier = "至少 " if truncated else ""
    ui_rows = ui_row_count if ui_row_count is not None else total
    result = (
        f"查询成功：{qualifier}{total} 行已取回；"
        f"前端画布可展示 {ui_rows} 行完整数据。"
        f"下列仅为推理用样本，列: {', '.join(str(c) for c in columns)}\n"
    )
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
    if max_rows is not None and total > max_rows:
        result += (
            f"... 样本仅展示前 {max_rows} 行；"
            f"其余行已在前端画布，请基于总行数总结，勿假设只有样本这么多。\n"
        )
    if truncated:
        result += "结果已达到服务端安全行数上限，实际数据可能更多；可收紧 WHERE 后再查。\n"
    return result


def _unique_column_names(columns: list[str]) -> list[str]:
    """Keep object-row keys lossless when a query returns duplicate aliases."""
    counts: dict[str, int] = {}
    unique: list[str] = []
    for raw_name in columns:
        name = str(raw_name)
        counts[name] = counts.get(name, 0) + 1
        unique.append(name if counts[name] == 1 else f"{name}_{counts[name]}")
    return unique


def infer_column_type(values: list[Any]) -> str:
    """Infer a conservative display type from raw database values."""
    observed: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            observed.add("boolean")
        elif isinstance(value, (datetime, date)):
            observed.add("datetime")
        elif isinstance(value, (Number, Decimal)):
            observed.add("number")
        elif isinstance(value, str):
            observed.add("string")
        else:
            observed.add("unknown")
    if not observed:
        return "unknown"
    return next(iter(observed)) if len(observed) == 1 else "unknown"


def build_result_component(
    columns: list[str],
    rows: list[tuple],
    sql: str,
    *,
    query_truncated: bool = False,
    max_frontend_rows: int = MAX_FRONTEND_ROWS,
) -> DataFrameComponent:
    """Build the user-facing dataframe without duplicating it in metadata."""
    names = _unique_column_names(columns)
    display_cap = max(1, max_frontend_rows)
    display_rows = rows[:display_cap]
    records: list[dict[str, Any]] = []
    for row in display_rows:
        records.append(
            {
                name: normalize_cell(row[index]) if index < len(row) else None
                for index, name in enumerate(names)
            }
        )

    typed_columns = [
        DataColumn(
            name=name,
            data_type=infer_column_type(
                [row[index] for row in rows if index < len(row)]
            ),
        )
        for index, name in enumerate(names)
    ]
    return DataFrameComponent(
        columns=typed_columns,
        rows=records,
        row_count=len(rows),
        row_count_is_exact=not query_truncated,
        displayed_row_count=len(records),
        truncated=query_truncated or len(rows) > display_cap,
        sql=sql,
    )


class RunSqlTool(Tool[RunSqlToolArgs]):
    """Execute read-only SQL using an injected SqlRunnerPool."""

    def __init__(
        self,
        pool: SqlRunnerPool,
        *,
        max_result_rows: int = 500,
        max_llm_rows: int = MAX_LLM_ROWS,
        max_frontend_rows: int | None = None,
    ) -> None:
        self._pool = pool
        self._max_result_rows = max(1, max_result_rows)
        self._max_llm_rows = max(1, max_llm_rows)
        # UI 与服务端硬上限对齐，避免「库取了 2000 行但画布只剩 500」
        self._max_frontend_rows = max(
            1, max_frontend_rows if max_frontend_rows is not None else max_result_rows
        )

    @property
    def name(self) -> str:
        return "run_sql"

    @property
    def description(self) -> str:
        return (
            "执行只读 SELECT。结果双通道：前端画布拿到完整结果集（服务端安全上限内），"
            "你只会看到少量样本用于推理——因此正式查询不要用 ROWNUM/LIMIT 人为截断；"
            "用 WHERE（含时间窗口）过滤即可。"
            "仅探查样例可限 1 行，或用户明确要求 Top N 时才限行。"
            "达梦不支持 LIMIT（探查用 ROWNUM）；MySQL 探查用 LIMIT。"
            "写 SQL 前应先 describe_table 确认字段。"
        )

    def get_args_schema(self) -> Type[RunSqlToolArgs]:
        return RunSqlToolArgs

    async def execute(self, context: ToolContext, args: RunSqlToolArgs) -> ToolResult:
        # 与 sql-agent tools.run_sql 一致：先校验，再进连接池
        if not validate_sql(args.sql):
            msg = "不安全的sql语句，拒绝执行"
            return ToolResult(
                success=False,
                result_for_llm=msg,
                error=msg,
                user_error=msg,
                metadata={"sql": args.sql},
            )

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                execution = await asyncio.to_thread(self._execute_once, args.sql)
                columns = execution.columns
                rows = execution.rows
                component = build_result_component(
                    columns,
                    rows,
                    args.sql,
                    query_truncated=execution.truncated,
                    max_frontend_rows=self._max_frontend_rows,
                )
                text = format_sql_result(
                    columns,
                    rows,
                    max_rows=self._max_llm_rows,
                    truncated=execution.truncated,
                    ui_row_count=component.displayed_row_count,
                )
                return ToolResult(
                    success=True,
                    result_for_llm=text,
                    ui_component=component,
                    metadata={
                        "row_count": component.row_count,
                        "row_count_is_exact": component.row_count_is_exact,
                        "displayed_row_count": component.displayed_row_count,
                        "columns": [column.name for column in component.columns],
                        "column_types": {
                            column.name: column.data_type
                            for column in component.columns
                        },
                        "sql": args.sql,
                        "truncated": component.truncated,
                    },
                )
            except PermissionError as e:
                msg = str(e) or "不安全的sql语句，拒绝执行"
                return ToolResult(
                    success=False,
                    result_for_llm=msg,
                    error=msg,
                    user_error=msg,
                    metadata={"sql": args.sql},
                )
            except Exception as e:
                last_error = e
                if attempt == 0:
                    logger.warning("SQL 执行失败，准备重试: %s", e)
                    continue
                logger.exception("SQL 执行重试后仍失败")
        diagnostic = f"SQL 执行失败（已重试）: {last_error}"
        public_message = "SQL 执行失败，请检查查询字段、条件或稍后重试。"
        return ToolResult(
            success=False,
            result_for_llm=diagnostic,
            error=diagnostic,
            user_error=public_message,
            metadata={"sql": args.sql, "error_code": "sql_execution_failed"},
        )

    def _execute_once(self, sql: str) -> SqlExecutionResult:
        """Run the entire blocking pool/driver operation on a worker thread."""
        with self._pool.borrow() as runner:
            return runner.execute_readonly(sql, max_rows=self._max_result_rows)


# Backward-compatible alias
RunSqlArgs = RunSqlToolArgs
