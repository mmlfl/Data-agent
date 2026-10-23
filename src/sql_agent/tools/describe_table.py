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
from sql_agent.retrieval.schema_catalog import AmbiguousTableError
from sql_agent.tools.schema_context import known_schema, remember_schema


class DescribeTableArgs(BaseModel):
    table_name: str = Field(description="表名，如 'EMPLOYEES' 或中文表注释对应的真实表名")
    refresh: bool = Field(default=False, description="仅在怀疑 SQLite 结构过期、与字段报错矛盾时设为true，回源刷新当前表；日常查询复用缓存")


class DescribeTableTool(Tool[DescribeTableArgs]):
    """Describe table columns via SQLite cache (fallback Dameng)."""

    def __init__(self, schema_cache: SchemaCache, *, catalog_provider=None) -> None:
        self._cache = schema_cache
        self._catalog_provider = catalog_provider

    @property
    def name(self) -> str:
        return "describe_table"

    @property
    def description(self) -> str:
        return (
            "查看指定表的所有字段信息（字段名、数据类型、是否可空、注释）。"
            "缺少字段结构或需要核对报错字段时使用；检索已给出当前完整结构时可直接复用。"
        )

    def get_args_schema(self) -> Type[DescribeTableArgs]:
        return DescribeTableArgs

    async def execute(
        self, context: ToolContext, args: DescribeTableArgs
    ) -> ToolResult:
        document, catalog, reused = None, None, None
        if self._catalog_provider is not None:
            try:
                catalog = await asyncio.to_thread(self._catalog_provider)
                key = catalog.resolve(args.table_name)
                document = catalog.documents([key])[0]
                if not document["columns"]:
                    document = None  # An empty cached table still needs a live describe.
                reused = known_schema(context, catalog.version, key)
            except AmbiguousTableError as error:
                return ToolResult(success=False, result_for_llm=str(error), user_error="表身份不唯一，请明确表名。")
            except (ValueError, FileNotFoundError):
                pass
        if args.refresh:
            # Canonical resolution prevents treating a qualified name as a
            # different database while the live cache supports one database.
            if "." in args.table_name and document is None:
                return ToolResult(success=False, result_for_llm="无法确认该 schema 属于当前数据源，请先定位准确表名。",
                                  user_error="请先确认准确表名。")
            name = document["table_name"] if document else args.table_name
            columns = await asyncio.to_thread(self._cache.get_table_info, name, refresh=True)
            document, reused = None, None
        elif document:
            columns = [{"column_name": c["name"], "data_type": c["data_type"],
                        "column_comment": c["comment"], "is_nullable": c["is_nullable"],
                        "data_length": c["data_length"]} for c in document["columns"]]
        else:
            columns = await asyncio.to_thread(self._cache.get_table_info, args.table_name)
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
        if document and not reused:
            remember_schema(context, catalog.version, [document])
        text = json.dumps(trimmed, ensure_ascii=False)
        if reused:
            text = json.dumps({"status": "reused", "table": document["table_key"],
                               "reference_tool_call_id": reused["tool_call_id"],
                               "message": "本轮已返回当前完整字段结构，请复用该工具结果。"}, ensure_ascii=False)
        return ToolResult(
            success=True,
            result_for_llm=text,
            ui_component=component,
            metadata={
                "table_name": args.table_name,
                "column_count": len(trimmed),
                "schema_reused": bool(reused),
            },
        )
