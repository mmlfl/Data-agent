"""run_sql tool — readonly SQL execution via SqlRunnerPool."""

from __future__ import annotations

import asyncio
import json
import time
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
from sql_agent.integrations.db.sql_errors import classify_sql_error
from sql_agent.retrieval.query_review import review_query
from sql_agent.integrations.db.sql_validate import (
    MAX_QUERY_ROWS,
    SqlValidationError,
    prepare_readonly_sql,
)

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
        if not value % 1:
            integer = int(value)
            return integer if abs(integer) <= 9007199254740991 else str(value)
        numeric = float(value)
        return numeric if math.isfinite(numeric) and Decimal(str(numeric)) == value else str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 9007199254740991:
        return str(value)
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
    reserved = {str(name) for name in columns}
    used: set[str] = set()
    unique: list[str] = []
    for raw_name in columns:
        name = str(raw_name)
        candidate, suffix = name, 2
        while candidate in used:
            candidate = f"{name}_{suffix}"
            suffix += 1
            while candidate in reserved or candidate in used:
                candidate = f"{name}_{suffix}"
                suffix += 1
        used.add(candidate)
        unique.append(candidate)
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
            source_name=str(columns[index]),
            numeric_encoding="exact_string" if any(
                isinstance(row[index], (int, Decimal)) and isinstance(normalize_cell(row[index]), str)
                for row in rows if index < len(row)
            ) else "native",
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
        max_result_rows: int = MAX_QUERY_ROWS,
        max_llm_rows: int = MAX_LLM_ROWS,
        max_frontend_rows: int | None = None,
        dialect: str | None = None,
    ) -> None:
        self._pool = pool
        self._max_result_rows = min(MAX_QUERY_ROWS, max(1, max_result_rows))
        self._dialect = dialect
        self._max_llm_rows = max(1, max_llm_rows)
        # UI 与服务端硬上限对齐，避免「库取了 2000 行但画布只剩 500」
        self._max_frontend_rows = min(
            self._max_result_rows,
            max(1, max_frontend_rows if max_frontend_rows is not None else self._max_result_rows),
        )

    @property
    def name(self) -> str:
        return "run_sql"

    @property
    def description(self) -> str:
        return (
            "执行经过 AST 校验的单条只读 SELECT，可包含只读 CTE 和子查询。"
            "服务器在 SQL 中强制限制最多 100 行并设置执行超时，已有更小限行会保留。"
            "前端展示限额内结果，你收到少量样本；达到上限时不能声称返回全部数据。"
            "请用 WHERE（含时间窗口）缩小范围，统计总量应使用 COUNT/SUM 等聚合。"
            "禁止写操作、锁定、变量赋值、危险函数和未审核的自定义函数。"
            "先确认字段；search_schema/find_join_path 已给出当前完整结构时可复用，不必重复 describe。"
            "多表聚合须提供 query_plan 明确结果粒度、指标、关联依据与防重复策略；"
            "仅筛选用 EXISTS，需要汇总先聚合再关联。错误后按 hint 修正，不要重复相同 SQL。"
        )

    def get_args_schema(self) -> Type[RunSqlToolArgs]:
        return RunSqlToolArgs

    async def execute(self, context: ToolContext, args: RunSqlToolArgs) -> ToolResult:
        budget = context.metadata.setdefault("sql_budget", {"calls": 0, "repairs": 0, "failed_sql": set()})
        max_calls = context.metadata.get("max_sql_attempts", 6)
        max_repairs = context.metadata.get("max_sql_repairs", 3)
        deadline = context.metadata.get("request_deadline")
        started = time.monotonic()

        def failure(code, hint, *, diagnostic=None, repairable=True, count=True):
            if count:
                budget["repairs"] += 1
            return ToolResult(
                success=False, error=code,
                result_for_llm=json.dumps({"error_code": code, "repairable": repairable,
                                          "hint": hint, "diagnostic": (diagnostic or "")[:2000],
                                          "remaining_sql_calls": max(0, max_calls - budget["calls"]),
                                          "remaining_repairs": max(0, max_repairs - budget["repairs"])}, ensure_ascii=False),
                user_error=hint,
                metadata={"sql": args.sql, "error_code": code, "repairable": repairable},
            )

        if (budget["calls"] >= max_calls or budget["repairs"] >= max_repairs
                or (deadline is not None and started >= deadline)):
            return failure("sql_budget_exhausted", "本轮 SQL 次数或时间预算已耗尽，请说明未完成原因或请求补充条件。",
                           repairable=False, count=False)
        budget["calls"] += 1
        try:
            prepared_sql = prepare_readonly_sql(args.sql, dialect=self._dialect, max_rows=self._max_result_rows)
        except SqlValidationError as error:
            return failure("sql_validation_failed", str(error))
        review = review_query(prepared_sql, self._dialect, args.query_plan)
        if review:
            return failure(review["error_code"], review["hint"], repairable=review["repairable"])
        if prepared_sql in budget["failed_sql"]:
            return failure("sql_unchanged_retry", "该 SQL 本轮已经失败；请依据错误修正或补查结构，不要原样重复。",
                           count=False)

        for attempt in range(2):
            try:
                if deadline is not None and time.monotonic() >= deadline:
                    return failure("sql_budget_exhausted", "本轮时间预算已耗尽，未再次执行 SQL。", repairable=False)
                execution = await asyncio.to_thread(self._execute_once, prepared_sql)
                executed_sql = execution.executed_sql or prepared_sql
                component = build_result_component(
                    execution.columns, execution.rows, executed_sql,
                    query_truncated=execution.truncated, max_frontend_rows=self._max_frontend_rows,
                )
                text = format_sql_result(
                    execution.columns, execution.rows, max_rows=self._max_llm_rows,
                    truncated=execution.truncated, ui_row_count=component.displayed_row_count,
                )
                return ToolResult(
                    success=True, result_for_llm=text, ui_component=component,
                    metadata={
                        "row_count": component.row_count, "row_count_is_exact": component.row_count_is_exact,
                        "displayed_row_count": component.displayed_row_count,
                        "columns": [column.name for column in component.columns],
                        "column_types": {column.name: column.data_type for column in component.columns},
                        "sql": executed_sql, "requested_sql": args.sql, "truncated": component.truncated,
                        "execution_time_ms": round((time.monotonic() - started) * 1000, 2),
                        "execution_attempts": attempt + 1, "system_row_limit": self._max_result_rows,
                        "query_plan": args.query_plan.model_dump() if args.query_plan else None,
                    },
                )
            except Exception as error:
                classified = classify_sql_error(error, self._dialect)
                if classified.retryable and attempt == 0:
                    logger.warning("Temporary SQL connection failure; retrying once (%s)", type(error).__name__)
                    continue
                budget["failed_sql"].add(prepared_sql)
                return failure(classified.code, classified.hint, diagnostic=str(error),
                               repairable=classified.repairable)

    def _execute_once(self, sql: str) -> SqlExecutionResult:
        """Run the entire blocking pool/driver operation on a worker thread."""
        with self._pool.borrow() as runner:
            return runner.execute_readonly(sql, max_rows=self._max_result_rows)


# Backward-compatible alias
RunSqlArgs = RunSqlToolArgs
