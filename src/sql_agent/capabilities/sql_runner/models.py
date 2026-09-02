"""SQL runner capability models."""

from pydantic import BaseModel, Field


class RunSqlToolArgs(BaseModel):
    """Arguments for run_sql tool."""

    sql: str = Field(description="要执行的 SELECT 查询语句（只允许只读查询）")
