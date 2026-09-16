"""Internal tool that turns a successful SQL result into a final insight card."""

from __future__ import annotations

import json
import logging
import math
import re
from typing import Any, Optional, Type

from pydantic import BaseModel, Field, ValidationError

from sql_agent.components import ChartSpec, DataColumn, FinalResultComponent
from sql_agent.core.llm import LlmMessage, LlmRequest, LlmService
from sql_agent.core.tool.base import Tool
from sql_agent.core.tool.models import ToolContext, ToolResult

logger = logging.getLogger(__name__)


class FinalizeResultArgs(BaseModel):
    question: str
    source_tool_call_id: str
    sql: str
    columns: list[DataColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    row_count_is_exact: bool = True
    truncated: bool = False
    sample_strategy: str = "systematic"
    draft: Optional[str] = None
    partial: bool = False


class _GeneratedFinalResult(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=1600)
    insights: list[str] = Field(default_factory=list, max_length=5)
    chart: ChartSpec = Field(default_factory=ChartSpec)
    warnings: list[str] = Field(default_factory=list, max_length=5)


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```$", "", stripped)
    try:
        loaded = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        loaded = json.loads(stripped[start : end + 1])
    if not isinstance(loaded, dict):
        raise ValueError("final result must be a JSON object")
    return loaded


def _fallback_chart(args: FinalizeResultArgs) -> ChartSpec:
    if args.row_count == 0 or not args.rows:
        return ChartSpec(type="none", reason="查询没有可视化数据")

    numeric = [c.name for c in args.columns if c.data_type == "number"]
    datetimes = [c.name for c in args.columns if c.data_type == "datetime"]
    categories = [
        c.name for c in args.columns if c.data_type in {"string", "boolean"}
    ]

    if (
        datetimes
        and numeric
        and not _dimension_has_duplicates(args.rows, datetimes[0], None)
    ):
        return ChartSpec(
            type="line",
            title="趋势概览",
            x_field=datetimes[0],
            y_fields=numeric[:3],
            reason="时间字段与数值字段适合趋势图",
        )
    if (
        categories
        and numeric
        and not _dimension_has_duplicates(args.rows, categories[0], None)
    ):
        return ChartSpec(
            type="bar",
            title="分类对比",
            x_field=categories[0],
            y_fields=numeric[:3],
            reason="分类字段与数值字段适合对比图",
        )
    if len(numeric) >= 2:
        return ChartSpec(
            type="scatter",
            title="数值关系",
            x_field=numeric[0],
            y_fields=[numeric[1]],
            reason="两个数值字段适合散点图",
        )
    return ChartSpec(type="none", reason="当前字段组合不适合可靠绘图")


def _dimension_has_duplicates(
    rows: list[dict[str, Any]], x_field: str, series_field: Optional[str]
) -> bool:
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (
            str(row.get(x_field)),
            str(row.get(series_field)) if series_field else "",
        )
        if key in seen:
            return True
        seen.add(key)
    return False


def _to_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, str) and value.strip():
        try:
            numeric = float(value)
        except ValueError:
            return None
        return numeric if math.isfinite(numeric) else None
    return None


def build_column_stats(
    columns: list[DataColumn], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Deterministic summary over the full loaded sample (not only the head)."""
    stats: dict[str, Any] = {"row_count": len(rows), "columns": {}}
    for column in columns:
        values = [row.get(column.name) for row in rows]
        non_null = [value for value in values if value is not None]
        entry: dict[str, Any] = {
            "null_count": len(values) - len(non_null),
            "non_null_count": len(non_null),
        }
        if column.data_type == "number":
            numbers = [
                number
                for number in (_to_number(value) for value in non_null)
                if number is not None
            ]
            if numbers:
                entry.update(
                    {
                        "min": min(numbers),
                        "max": max(numbers),
                        "sum": sum(numbers),
                        "avg": sum(numbers) / len(numbers),
                    }
                )
        else:
            distinct = {str(value) for value in non_null}
            entry["distinct_count"] = len(distinct)
            if len(distinct) <= 8:
                entry["distinct_values"] = sorted(distinct)[:8]
        stats["columns"][column.name] = entry
    return stats


def _validate_chart(
    requested: ChartSpec, args: FinalizeResultArgs
) -> tuple[ChartSpec, Optional[str]]:
    if args.row_count == 0:
        return ChartSpec(type="none", reason="查询没有返回数据"), None
    if requested.type == "none":
        return requested, None

    types = {column.name: column.data_type for column in args.columns}
    if not requested.x_field or requested.x_field not in types:
        return _fallback_chart(args), "图表横轴字段无效，已自动调整"
    valid_y = [field for field in requested.y_fields if field in types]
    if not valid_y:
        return _fallback_chart(args), "图表数值字段无效，已自动调整"

    numeric_y = [field for field in valid_y if types[field] == "number"]
    if requested.type in {"bar", "line", "area", "pie"} and not numeric_y:
        return _fallback_chart(args), "图表缺少数值字段，已自动调整"
    if requested.type == "scatter":
        if types[requested.x_field] != "number" or not numeric_y:
            return _fallback_chart(args), "散点图字段类型无效，已自动调整"
        numeric_y = numeric_y[:1]
    if requested.type == "pie":
        numeric_y = numeric_y[:1]

    adjustments: list[str] = []
    series_field = requested.series_field
    if series_field and (
        series_field not in types
        or types[series_field] not in {"string", "boolean", "datetime"}
    ):
        series_field = None
        adjustments.append("系列字段无效，已移除")

    if requested.type == "pie":
        distinct_categories = {
            str(row.get(requested.x_field)) for row in args.rows
        }
        if len(distinct_categories) > 12:
            return _fallback_chart(args), "饼图类别过多，已自动调整"

    has_duplicates = _dimension_has_duplicates(
        args.rows, requested.x_field, series_field
    )
    aggregation = requested.aggregation
    if (
        requested.type != "scatter"
        and aggregation == "none"
        and has_duplicates
    ):
        aggregation = "sum"
        adjustments.append("存在重复维度，已按 sum 聚合后再绘图")

    return (
        requested.model_copy(
            update={
                "y_fields": numeric_y,
                "series_field": series_field,
                "aggregation": aggregation,
            }
        ),
        "；".join(adjustments) or None,
    )


class FinalizeResultTool(Tool[FinalizeResultArgs]):
    """System-only result finalizer; it is never offered to the main LLM loop."""

    def __init__(self, llm_service: LlmService, max_retries: int = 1) -> None:
        self._llm = llm_service
        self._max_retries = max(0, max_retries)

    @property
    def name(self) -> str:
        return "finalize_result"

    @property
    def description(self) -> str:
        return "将最终 SQL 查询结果整理为中文总结、洞察与安全图表规范"

    def get_args_schema(self) -> Type[FinalizeResultArgs]:
        return FinalizeResultArgs

    async def execute(
        self, context: ToolContext, args: FinalizeResultArgs
    ) -> ToolResult:
        generated: Optional[_GeneratedFinalResult] = None
        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._llm.send_request(
                    self._build_request(context, args, attempt, last_error)
                )
                if not response.content:
                    raise ValueError("LLM returned an empty final result")
                generated = _GeneratedFinalResult.model_validate(
                    _extract_json(response.content)
                )
                break
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning(
                    "Finalize result attempt %d failed: %s", attempt + 1, exc
                )
            except Exception as exc:  # provider/network failures use safe fallback
                last_error = exc
                logger.exception("Finalize result request failed")
                break

        fallback_used = generated is None
        if generated is None:
            generated = self._fallback_result(args)

        chart, chart_warning = _validate_chart(generated.chart, args)
        warnings = list(generated.warnings)
        if args.row_count > len(args.rows) or args.truncated:
            sample_note = (
                f"AI 总结基于 {len(args.rows)} 行"
                f"{'系统抽样' if args.sample_strategy == 'systematic' else '样本'}"
            )
            if args.truncated:
                total = (
                    str(args.row_count)
                    if args.row_count_is_exact
                    else f"至少 {args.row_count}"
                )
                sample_note += f"；服务端已限制结果，返回 {total} 行"
            warnings.append(sample_note)
        if args.partial:
            warnings.append("工具调用达到上限，结论基于最后一次成功查询")
        if chart_warning:
            warnings.append(chart_warning)
        if fallback_used:
            warnings.append("AI 总结暂不可用，已展示确定性查询摘要")

        component = FinalResultComponent(
            source_tool_call_id=args.source_tool_call_id,
            title=generated.title,
            summary=generated.summary,
            insights=generated.insights,
            chart=chart,
            warnings=list(dict.fromkeys(warnings)),
        )
        return ToolResult(
            success=True,
            result_for_llm=component.summary,
            ui_component=component,
            metadata={
                "source_tool_call_id": args.source_tool_call_id,
                "row_count": args.row_count,
                "chart_type": component.chart.type,
                "fallback_used": fallback_used,
            },
        )

    def _build_request(
        self,
        context: ToolContext,
        args: FinalizeResultArgs,
        attempt: int,
        last_error: Optional[Exception],
    ) -> LlmRequest:
        columns = [
            {"name": column.name, "data_type": column.data_type}
            for column in args.columns
        ]
        payload = {
            "question": args.question,
            "sql": args.sql,
            "columns": columns,
            "row_count": args.row_count,
            "row_count_is_exact": args.row_count_is_exact,
            "sample_strategy": args.sample_strategy,
            "rows_sample": args.rows,
            "column_stats": build_column_stats(args.columns, args.rows),
            "truncated": args.truncated,
            "draft_answer": (args.draft or "")[:1200],
        }
        retry_note = (
            f"\n上一次输出校验失败：{last_error}。只返回合法 JSON。"
            if attempt > 0 and last_error
            else ""
        )
        system_prompt = (
            "你是严谨的数据分析助手。仅根据给定 SQL 结果生成中文结论，不得虚构。"
            "必须返回一个 JSON 对象，字段为："
            "title(string), summary(string), insights(string[]), "
            "chart({type,title,x_field,y_fields,series_field,aggregation,reason}), "
            "warnings(string[])。"
            "chart.type 只能是 bar/line/area/pie/scatter/none；所有字段名必须来自 columns。"
            "aggregation 只能是 none/sum/avg/min/max/count。"
            "仅当横轴与系列组合唯一时使用 none；存在重复维度时必须指定明确聚合。"
            "优先参考 column_stats 中的确定性统计，再结合 rows_sample 举例。"
            "无数据时 chart.type=none。summary 先直接回答问题，再说明关键数字。"
            f"{retry_note}"
        )
        return LlmRequest(
            messages=[
                LlmMessage(
                    role="user",
                    content=json.dumps(payload, ensure_ascii=False),
                )
            ],
            tools=None,
            user=context.user,
            stream=False,
            temperature=0.1,
            max_tokens=1400,
            system_prompt=system_prompt,
            response_format="json_object",
        )

    @staticmethod
    def _fallback_result(args: FinalizeResultArgs) -> _GeneratedFinalResult:
        if args.row_count == 0:
            summary = "查询执行成功，但没有返回符合当前条件的数据。"
        else:
            qualifier = "" if args.row_count_is_exact else "至少 "
            summary = (
                f"查询已完成，共返回 {qualifier}{args.row_count} 行、"
                f"{len(args.columns)} 个字段。"
            )
        return _GeneratedFinalResult(
            title="查询结果",
            summary=summary,
            insights=[],
            chart=_fallback_chart(args),
            warnings=[],
        )
