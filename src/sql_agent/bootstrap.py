"""Shared agent bootstrap for CLI and HTTP server."""

from __future__ import annotations

import os

from sql_agent.core.agent import Agent, AgentConfig
from sql_agent.core.registry import ToolRegistry
from sql_agent.integrations.deepseek import DeepSeekLlmService
from sql_agent.integrations.db import InMemoryAgentMemory
from sql_agent.tools import DescribeTableTool, ListTablesTool, RunSqlTool
from sql_agent.core.user import FixedUserResolver
from sql_agent.integrations.db import DbSettings, SchemaCache, create_sql_runner_pool


def build_agent(*, with_db: bool | None = None) -> Agent:
    """Build Agent from environment. with_db defaults to WITH_DB env."""
    if with_db is None:
        with_db = os.getenv("WITH_DB", "false").lower() == "true"

    llm = DeepSeekLlmService()
    registry = ToolRegistry()

    if with_db:
        settings = DbSettings()
        pool = create_sql_runner_pool(settings)
        cache = SchemaCache(pool=pool, settings=settings)
        force_sync = os.getenv("SCHEMA_CACHE_FORCE_SYNC", "false").lower() == "true"
        cache_info = cache.ensure_ready(force=force_sync)
        print(
            f"Schema cache [{cache_info['status']}]: "
            f"{cache_info['dialect']} · {cache_info['table_count']} tables · "
            f"{cache_info['cache_path']}"
        )
        registry.register(ListTablesTool(cache), access_groups=["user"])
        registry.register(DescribeTableTool(cache), access_groups=["user"])
        registry.register(RunSqlTool(pool), access_groups=["user"])

    return Agent(
        llm_service=llm,
        tool_registry=registry,
        user_resolver=FixedUserResolver(),
        agent_memory=InMemoryAgentMemory(),
        config=AgentConfig(
            stream_responses=os.getenv("STREAM_RESPONSES", "true").lower() == "true",
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        ),
    )
