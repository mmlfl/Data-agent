"""Factory helpers to create SqlRunner / SqlRunnerPool by DB_DIALECT."""

from __future__ import annotations

from typing import Callable, Type

from sql_agent.capabilities.sql_runner import SqlRunner
from sql_agent.integrations.db.dameng.sql_runner import DamengRunner
from sql_agent.integrations.db.db_settings import DbSettings
from sql_agent.integrations.db.sql_runner_pool import SqlRunnerPool
from sql_agent.integrations.db.mysql.sql_runner import MySQLRunner

SqlRunnerFactory = Callable[[DbSettings], SqlRunner]

_DIALECT_ALIASES = {
    "dm": "dm",
    "dameng": "dm",
    "达梦": "dm",
    "mysql": "mysql",
}


def normalize_dialect(name: str | None) -> str:
    key = str(name or "dm").strip().lower()
    normalized = _DIALECT_ALIASES.get(key)
    if normalized is None:
        raise ValueError(f"未知数据库方言: {name!r}（支持: dm, mysql）")
    return normalized


def get_sql_runner_class(dialect: str | None = None) -> Type[SqlRunner]:
    key = normalize_dialect(dialect)
    if key == "mysql":
        return MySQLRunner
    return DamengRunner


def create_sql_runner(settings: DbSettings | None = None) -> SqlRunner:
    settings = settings or DbSettings()
    runner_cls = get_sql_runner_class(settings.db_dialect)
    runner = runner_cls(settings)
    runner.connect()
    return runner


def create_sql_runner_pool(
    settings: DbSettings | None = None,
    pool_size: int | None = None,
) -> SqlRunnerPool:
    settings = settings or DbSettings()
    size = pool_size if pool_size is not None else settings.db_pool_size
    runner_cls = get_sql_runner_class(settings.db_dialect)
    return SqlRunnerPool(factory=lambda: runner_cls(settings), pool_size=size)


def create_dameng_runner_pool(settings: DbSettings | None = None) -> SqlRunnerPool:
    """Create a pool forced to DamengRunner."""
    settings = settings or DbSettings()
    size = settings.db_pool_size
    return SqlRunnerPool(factory=lambda: DamengRunner(settings), pool_size=size)


# Backward-compatible aliases
get_connection_factory = get_sql_runner_class
create_connection = create_sql_runner
create_pool = create_sql_runner_pool
create_dameng_pool = create_dameng_runner_pool
