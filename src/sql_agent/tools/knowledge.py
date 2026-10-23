"""Optional retrieval is exposed as tools, not injected into every system prompt."""

import asyncio
import json

from pydantic import BaseModel, Field

from sql_agent.core.tool.base import Tool
from sql_agent.core.tool.models import ToolResult
from sql_agent.tools.schema_context import remember_schema


class SearchQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=8192, description="补齐已明确对话条件后的完整业务问题")


class JoinPathArgs(BaseModel):
    source_table: str = Field(min_length=1, description="起点表，建议使用 schema.table")
    target_table: str = Field(min_length=1, description="目标表，建议使用 schema.table")
    relation_ids: list[str] = Field(default_factory=list, max_length=30, description="仅在连接角色歧义时指定返回过的规则ID；为空使用所有已确认规则")


class KnowledgeTool(Tool):
    def __init__(self, service, kind):
        self.service = service
        self.kind = kind

    @property
    def name(self):
        return self.kind

    @property
    def description(self):
        return {
            "search_schema": "用自然语言对单表结构做 Dense+BM25 检索，返回当前 SQLite 完整结构；不足时用 list_tables/describe_table 补查。",
            "search_sql_memory": "检索当前用户确认过的问题与 SQL 参考，最多3条。必须重新适配本题时间、指标、粒度和条件并执行，不照抄历史答案。",
            "find_join_path": "查询已确认逻辑关系，BFS最多3跳、50节点、100条边，只返回一条路径及中间表结构。空结果不证明业务无关系；歧义时参考来源后限定规则。",
        }[self.kind]

    def get_args_schema(self):
        return JoinPathArgs if self.kind == "find_join_path" else SearchQuestion

    async def execute(self, context, args):
        try:
            if self.kind == "search_schema":
                cache = context.metadata.get("schema_searches", {})
                cached = cache.get(args.question.strip())
                if cached:
                    try:
                        catalog = await asyncio.to_thread(self.service.catalog)
                    except Exception:
                        catalog = None  # Optimization must not disable fail-open retrieval.
                    visible = context.metadata.get("visible_tool_ids")
                    if (catalog and cached["version"] == catalog.version
                            and (visible is None or cached["tool_call_id"] in visible)):
                        return ToolResult(success=True, result_for_llm=json.dumps({
                            "status": "reused", "reference_tool_call_id": cached["tool_call_id"],
                            "message": "相同问题的当前版本表结构已在上述工具结果中，请直接复用；缺少结构再 describe_table。",
                        }, ensure_ascii=False), metadata={"retrieval_status": "reused"})
            if self.kind == "find_join_path":
                result = await asyncio.to_thread(self.service.join_path, args.source_table, args.target_table,
                                                context.user.id, args.relation_ids)
            else:
                method = self.service.search_schema if self.kind == "search_schema" else self.service.search_memory
                result = await asyncio.to_thread(method, args.question, context.user.id)
            if result.get("schema_version"):
                remember_schema(context, result["schema_version"], result.get("tables", []))
                if self.kind == "search_schema" and context.metadata.get("tool_call_id"):
                    context.metadata.setdefault("schema_searches", {})[args.question.strip()] = {
                        "version": result["schema_version"], "tool_call_id": context.metadata["tool_call_id"],
                    }
            return ToolResult(success=True, result_for_llm=json.dumps(result, ensure_ascii=False),
                              metadata={"retrieval_status": result["status"]})
        except ValueError as error:
            return ToolResult(success=False, result_for_llm=str(error), user_error="表身份未明确，请先查找准确表名。")
