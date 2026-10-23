"""Shared agent bootstrap for CLI and HTTP server."""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from sql_agent.core.agent import Agent, AgentConfig
from sql_agent.core.registry import ToolRegistry
from sql_agent.core.system_prompt import DefaultSystemPromptBuilder
from sql_agent.core.user import FixedUserResolver
from sql_agent.integrations.db import (
    DbSettings,
    InMemoryAgentMemory,
    SchemaCache,
    create_sql_runner_pool,
)
from sql_agent.integrations.deepseek import DeepSeekLlmService
from sql_agent.tools import (
    DescribeTableTool,
    FinalizeResultTool,
    ListTablesTool,
    RunSqlTool,
)


@dataclass
class RuntimeBundle:
    agent: Agent
    schema_cache: Optional[SchemaCache]
    cache_info: Optional[dict]
    knowledge_service: object | None = None


def build_runtime(*, with_db: bool | None = None) -> RuntimeBundle:
    """Build Agent (+ optional SchemaCache). Always runs ensure_ready when WITH_DB."""
    if with_db is None:
        with_db = os.getenv("WITH_DB", "false").lower() == "true"

    llm = DeepSeekLlmService()
    registry = ToolRegistry()
    schema_cache: Optional[SchemaCache] = None
    cache_info: Optional[dict] = None
    settings: Optional[DbSettings] = None
    knowledge_service = None

    if with_db:
        settings = DbSettings()
        pool = create_sql_runner_pool(settings)
        schema_cache = SchemaCache(pool=pool, settings=settings)
        force_sync = os.getenv("SCHEMA_CACHE_FORCE_SYNC", "false").lower() == "true"
        print(
            f"[schema-cache] ensuring ready "
            f"(dialect={settings.db_dialect}, force={force_sync}, path={schema_cache.db_path}) ..."
        )
        cache_info = schema_cache.ensure_ready(force=force_sync)
        print(
            f"[schema-cache] [{cache_info['status']}] "
            f"{cache_info['dialect']} · {cache_info['table_count']} tables · "
            f"{cache_info['cache_path']}"
        )
        if cache_info["table_count"] == 0:
            print(
                "[schema-cache] WARNING: 0 tables synced. "
                "检查 DB 账号是否有业务表（达梦 OWNER=USER），或手动 POST /api/cache/sync"
            )
        registry.register(ListTablesTool(schema_cache), access_groups=["user"])
        registry.register(
            RunSqlTool(
                pool,
                max_result_rows=settings.db_max_result_rows,
                max_frontend_rows=settings.db_max_result_rows,
                dialect=settings.db_dialect,
            ),
            access_groups=["user"],
        )
        registry.register(
            FinalizeResultTool(llm),
            access_groups=["user"],
            expose_to_llm=False,
        )
        from sql_agent.capabilities.knoledge_store.experience_models import stable_hash
        from sql_agent.integrations.db.experience_store import ExperienceStore
        from sql_agent.integrations.milvus.memory_store import KnowledgeVectors
        from sql_agent.integrations.milvus.settings import MilvusSettings
        from sql_agent.services.knowledge_service import KnowledgeService
        from sql_agent.tools.knowledge import KnowledgeTool

        rag_settings = MilvusSettings()
        database_id = rag_settings.rag_database_id.strip() or "db:" + stable_hash(
            [settings.db_dialect, settings.db_host, settings.db_port, settings.db_database, settings.db_user]
        )[:32]
        knowledge_path = Path(rag_settings.knowledge_db_path)
        if not knowledge_path.is_absolute():
            knowledge_path = Path(__file__).resolve().parents[2] / knowledge_path
        knowledge_service = KnowledgeService(
            ExperienceStore(knowledge_path), cache_path=schema_cache.db_path,
            database_id=database_id, tenant_id=rag_settings.rag_tenant_id,
            dialect=settings.db_dialect, vectors=KnowledgeVectors(rag_settings),
        )
        registry.register(DescribeTableTool(schema_cache, catalog_provider=knowledge_service.catalog), access_groups=["user"])
        for name in ("search_schema", "search_sql_memory", "find_join_path"):
            registry.register(KnowledgeTool(knowledge_service, name), access_groups=["user"])

    dialect = settings.db_dialect if settings else os.getenv("DB_DIALECT", "dm")
    max_result_rows = (
        settings.db_max_result_rows
        if settings
        else int(os.getenv("DB_MAX_RESULT_ROWS", "100"))
    )
    agent = Agent(
        llm_service=llm,
        tool_registry=registry,
        user_resolver=FixedUserResolver(),
        agent_memory=InMemoryAgentMemory(),
        system_prompt_builder=DefaultSystemPromptBuilder(
            dialect=dialect,
            max_result_rows=max_result_rows,
        ),
        config=AgentConfig(
            max_tool_iterations=int(os.getenv("MAX_TOOL_ITERATIONS", "10")),
            max_sql_attempts=int(os.getenv("MAX_SQL_ATTEMPTS", "6")),
            max_sql_repairs=int(os.getenv("MAX_SQL_REPAIRS", "3")),
            max_request_seconds=float(os.getenv("MAX_REQUEST_SECONDS", "180")),
            stream_responses=os.getenv("STREAM_RESPONSES", "true").lower() == "true",
            auto_finalize_results=os.getenv(
                "AUTO_FINALIZE_RESULTS", "true"
            ).lower()
            == "true",
            max_finalize_rows=int(os.getenv("MAX_FINALIZE_ROWS", "20")),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        ),
        knowledge_service=knowledge_service,
    )
    return RuntimeBundle(agent=agent, schema_cache=schema_cache, cache_info=cache_info, knowledge_service=knowledge_service)


def build_agent(*, with_db: bool | None = None) -> Agent:
    """Backward-compatible: return Agent only."""
    return build_runtime(with_db=with_db).agent
