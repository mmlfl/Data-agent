"""SQL runner capability models."""

from dataclasses import dataclass

from pydantic import BaseModel, Field

MAX_QUERY_ROWS = 100


@dataclass(frozen=True, slots=True)
class SqlExecutionResult:
    """A bounded result returned by a database runner."""

    columns: list[str]
    rows: list[tuple]
    truncated: bool = False
    executed_sql: str | None = None


class RunSqlToolArgs(BaseModel):
    """Arguments for run_sql tool."""

    sql: str = Field(description="要执行的 SELECT 查询语句（只允许只读查询）")
