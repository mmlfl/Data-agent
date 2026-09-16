"""Server dependencies — singleton agent + schema cache."""

from __future__ import annotations

from typing import Optional

from sql_agent.bootstrap import RuntimeBundle, build_runtime
from sql_agent.core.agent import Agent
from sql_agent.integrations.db import SchemaCache

_bundle: Optional[RuntimeBundle] = None


def get_runtime() -> RuntimeBundle:
    """Build once on first use (prefer calling from app lifespan at startup)."""
    global _bundle
    if _bundle is None:
        _bundle = build_runtime()
    return _bundle


def warmup_runtime() -> RuntimeBundle:
    """Force build at process startup so schema sync runs before first request."""
    return get_runtime()


def get_agent() -> Agent:
    return get_runtime().agent


def get_schema_cache() -> Optional[SchemaCache]:
    return get_runtime().schema_cache
