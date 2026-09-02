"""Local SQLite schema metadata cache (project extension; not Vanna SqliteRunner)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sql_agent.integrations.db.db_settings import DbSettings
from sql_agent.integrations.db.sql_runner_pool import SqlRunnerPool

logger = logging.getLogger(__name__)


class SchemaCache:
    """Local SQLite cache of table/column metadata.

    Tools query SQLite first; on miss, fall back to the live database and upsert cache.
    Each DB_DIALECT uses its own SQLite file (metadata_dm.db / metadata_mysql.db).

    Note: This is NOT Vanna's SqliteRunner. Vanna's SqliteRunner executes SQL against
    a business SQLite database. SchemaCache only stores schema metadata for dm/mysql.
    """

    def __init__(
        self,
        pool: SqlRunnerPool,
        settings: Optional[DbSettings] = None,
        db_path: Optional[str | Path] = None,
    ) -> None:
        self.pool = pool
        self.settings = settings or DbSettings()
        self.db_path = Path(db_path) if db_path else self.settings.resolve_cache_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _init_tables(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tables (
                    table_name    TEXT PRIMARY KEY,
                    schema_name   TEXT,
                    table_comment TEXT,
                    sync_time     DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS columns (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name     TEXT,
                    column_name    TEXT,
                    data_type      TEXT,
                    column_comment TEXT,
                    is_nullable    TEXT,
                    data_length    INTEGER,
                    FOREIGN KEY (table_name) REFERENCES tables(table_name)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_columns_table_name ON columns(table_name)"
            )

    def table_count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM tables").fetchone()
            return int(row[0]) if row else 0

    def is_ready(self) -> bool:
        """True when cache file exists and contains synced table metadata."""
        if not self.db_path.is_file():
            return False
        try:
            return self.table_count() > 0
        except sqlite3.Error:
            return False

    def ensure_ready(self, *, force: bool = False) -> dict:
        """Use existing cache, or run a full sync from the live database first."""
        dialect = self.settings.db_dialect
        if force or not self.is_ready():
            if force and self.is_ready():
                logger.info("强制刷新 %s 元数据缓存", dialect)
            else:
                logger.info("未检测到 %s 元数据缓存，开始全量同步", dialect)
            self.sync()
            status = "synced"
        else:
            logger.info(
                "使用已有 %s 元数据缓存：%s（%d 张表）",
                dialect,
                self.db_path,
                self.table_count(),
            )
            status = "cached"

        return {
            "status": status,
            "dialect": dialect,
            "cache_path": str(self.db_path),
            "table_count": self.table_count(),
        }

    def sync(self) -> None:
        """Pull full schema from the live database (dm or mysql) into SQLite."""
        dialect = self.settings.db_dialect
        logger.info("开始从 %s 全量同步元数据到 SQLite ...", dialect)
        start = datetime.now()
        with self.pool.borrow() as runner:
            tables, columns = runner.fetch_schema_metadata()

        with sqlite3.connect(self.db_path) as sqlite:
            sqlite.execute("DELETE FROM columns")
            sqlite.execute("DELETE FROM tables")
            for table_name, owner, comment in tables:
                sqlite.execute(
                    "INSERT INTO tables (table_name, schema_name, table_comment) "
                    "VALUES (?, ?, ?)",
                    (table_name, owner, comment or ""),
                )
            for col in columns:
                table_name, col_name, data_type, nullable, data_len, col_comment = col
                sqlite.execute(
                    "INSERT INTO columns "
                    "(table_name, column_name, data_type, column_comment,"
                    " is_nullable, data_length) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        table_name,
                        col_name,
                        data_type,
                        str(col_comment or ""),
                        str(nullable or ""),
                        int(data_len) if data_len is not None else 0,
                    ),
                )
        elapsed = (datetime.now() - start).total_seconds()
        logger.info(
            "同步完成：%s 张表，%s 个字段，耗时 %.1fs",
            len(tables),
            len(columns),
            elapsed,
        )

    def search_tables(self, keyword: str) -> List[dict]:
        """SQLite first; if empty, query live DB and upsert hits."""
        rows = self._search_tables_sqlite(keyword)
        if rows:
            return rows

        logger.info("SQLite 未命中表搜索 '%s'，回源 %s", keyword, self.settings.db_dialect)
        with self.pool.borrow() as runner:
            live = runner.search_tables(keyword)
        if live:
            self._upsert_tables(live)
        return live

    def get_table_info(self, table_name: str) -> List[dict]:
        """SQLite first; if empty, describe on live DB and upsert."""
        rows = self._get_table_info_sqlite(table_name)
        if rows:
            return rows

        logger.info(
            "SQLite 未命中表结构 '%s'，回源 %s",
            table_name,
            self.settings.db_dialect,
        )
        with self.pool.borrow() as runner:
            live = runner.describe_table(table_name)
        if live:
            self._upsert_table_columns(table_name, live)
        return live

    def _search_tables_sqlite(self, keyword: str) -> List[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT table_name, schema_name, table_comment FROM tables "
                "WHERE table_name LIKE ? OR table_comment LIKE ?",
                (f"%{keyword}%", f"%{keyword}%"),
            ).fetchall()
            return [dict(r) for r in rows]

    def _get_table_info_sqlite(self, table_name: str) -> List[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT column_name, data_type, column_comment,"
                "       is_nullable, data_length "
                "FROM columns WHERE UPPER(table_name) = UPPER(?) "
                "ORDER BY id",
                (table_name,),
            ).fetchall()
            return [dict(r) for r in rows]

    def _upsert_tables(self, tables: List[dict]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            for t in tables:
                conn.execute(
                    "INSERT INTO tables (table_name, schema_name, table_comment) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT(table_name) DO UPDATE SET "
                    "schema_name=excluded.schema_name, "
                    "table_comment=excluded.table_comment, "
                    "sync_time=CURRENT_TIMESTAMP",
                    (
                        t.get("table_name"),
                        t.get("schema_name"),
                        t.get("table_comment") or "",
                    ),
                )

    def _upsert_table_columns(self, table_name: str, columns: List[dict]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO tables (table_name, schema_name, table_comment) "
                "VALUES (?, '', '') "
                "ON CONFLICT(table_name) DO NOTHING",
                (table_name,),
            )
            conn.execute(
                "DELETE FROM columns WHERE UPPER(table_name) = UPPER(?)",
                (table_name,),
            )
            for c in columns:
                conn.execute(
                    "INSERT INTO columns "
                    "(table_name, column_name, data_type, column_comment,"
                    " is_nullable, data_length) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        table_name,
                        c.get("column_name"),
                        c.get("data_type"),
                        c.get("column_comment") or "",
                        str(c.get("is_nullable") or ""),
                        int(c.get("data_length") or 0),
                    ),
                )
