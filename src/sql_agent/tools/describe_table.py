"""describe_table tool — column metadata by table name."""

from __future__ import annotations

import asyncio
import json
from typing import Type

from pydantic import BaseModel, Field

from sql_agent.components import SchemaColumn, TableSchemaComponent
from sql_agent.core.tool.base import Tool
from sql_agent.core.tool.models import ToolContext, ToolResult
from sql_agent.integrations.db.schema_cache import SchemaCache


class DescribeTableArgs(BaseModel):
    table_name: str = Field(description="表名，如 'EMPLOYEES' 或中文表注释对应的真实表名")


class DescribeTableTool(Tool[DescribeTableArgs]):
    """Describe table columns via SQLite cache (fallback Dameng)."""

    def __init__(self, schema_cache: SchemaCache) -> None:
        self._cache = schema_cache

    @property
    def name(self) -> str:
        return "describe_table"

    @property
    def description(self) -> str:
        return (
            "查看指定表的所有字段信息（字段名、数据类型、是否可空、注释）。"
            "拿到表名后务必先看字段，再写 SQL。"
        )

    def get_args_schema(self) -> Type[DescribeTableArgs]:
        return DescribeTableArgs

    async def execute(
        self, context: ToolContext, args: DescribeTableArgs
    ) -> ToolResult:
        columns = await asyncio.to_thread(
            self._cache.get_table_info, args.table_name
        )
        if not columns:
            return ToolResult(
                success=False,
                result_for_llm=f"未找到表 '{args.table_name}'",
                error=f"table not found: {args.table_name}",
            )
        trimmed = [
            {
                "column_name": c["column_name"],
                "data_type": c.get("data_type"),
                "is_nullable": c.get("is_nullable"),
                "data_length": c.get("data_length"),
                "column_comment": c.get("column_comment"),
            }
            for c in columns
        ]
        component = TableSchemaComponent(
            table_name=args.table_name,
            columns=[SchemaColumn.model_validate(column) for column in trimmed],
        )
        return ToolResult(
            success=True,
            result_for_llm=json.dumps(trimmed, ensure_ascii=False),
            ui_component=component,
            metadata={
                "table_name": args.table_name,
                "column_count": len(trimmed),
            },
        )
