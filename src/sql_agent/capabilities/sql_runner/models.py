"""SQL runner capability models."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

MAX_QUERY_ROWS = 100


@dataclass(frozen=True, slots=True)
class SqlExecutionResult:
    """A bounded result returned by a database runner."""

    columns: list[str]
    rows: list[tuple]
    truncated: bool = False
    executed_sql: str | None = None


class QueryPlan(BaseModel):
    """A compact business contract, not hidden reasoning or proof of correctness."""

    grain: str = Field(min_length=1, max_length=500, description="结果每行代表什么，如每月每门课程")
    metrics: list[str] = Field(min_length=1, max_length=15, description="指标定义、来源表/字段与聚合方式")
    filters: list[str] = Field(default_factory=list, max_length=20, description="本题时间范围、状态、租户等条件；无要求不要猜测")
    join_purpose: str = Field(min_length=1, max_length=1000, description="各关联用途、业务角色及关系依据；无依据应向用户澄清")
    fanout_strategy: Literal["exists", "preaggregate", "count_distinct", "verified_cardinality", "not_applicable"] = Field(
        description="防重复策略：仅筛选用exists，先聚合用preaggregate，唯一计数用count_distinct；已核实基数才用verified_cardinality")
    evidence: str = Field(min_length=1, max_length=1500, description="说明策略与本题口径如何匹配；声明基数已核实时须给出用户确认/唯一键等依据，不能只凭同名字段")


class RunSqlToolArgs(BaseModel):
    """Arguments for run_sql tool."""

    sql: str = Field(description="要执行的 SELECT 查询语句（只允许只读查询）")
    question: str | None = Field(default=None, max_length=8192,
                                description="本次查询解决的完整业务问题；补齐已明确的上文条件，不添加猜测，用于用户确认和后续SQL参考")
    query_plan: QueryPlan | None = Field(default=None, description="多表聚合必须提供统计口径；简单查询可省略")
