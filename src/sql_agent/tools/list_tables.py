"""list_tables tool — search tables by name or comment."""

from __future__ import annotations

import json
from typing import Type

from pydantic import BaseModel, Field

from sql_agent.core.tool.base import Tool
from sql_agent.core.tool.models import ToolContext, ToolResult
from sql_agent.integrations.db.schema_cache import SchemaCache


class ListTablesArgs(BaseModel):
    keyword: str = Field(description="搜索关键词，如'工单'、'USER'，匹配表名或表注释")


class ListTablesTool(Tool[ListTablesArgs]):
    """Search possible tables via SQLite cache (fallback Dameng)."""

    def __init__(self, schema_cache: SchemaCache) -> None:
        self._cache = schema_cache

    @property
    def name(self) -> str:
        return "list_tables"

    @property
    def description(self) -> str:
        return (
            "按关键词模糊搜索数据库中的表名和表注释，返回可能相关的表列表。"
            "定位表时使用；拿到候选表名后应再用 describe_table 看字段。"
        )

    def get_args_schema(self) -> Type[ListTablesArgs]:
        return ListTablesArgs

    async def execute(self, context: ToolContext, args: ListTablesArgs) -> ToolResult:
        rows = self._cache.search_tables(args.keyword)
        if not rows:
            return ToolResult(
                success=True,
                result_for_llm=f"未找到与 '{args.keyword}' 相关的表",
            )
        return ToolResult(
            success=True,
            result_for_llm=json.dumps(rows, ensure_ascii=False),
            metadata={"count": len(rows)},
        )
