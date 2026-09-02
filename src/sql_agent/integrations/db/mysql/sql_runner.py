"""MySQL implementation of SqlRunner."""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

from sql_agent.capabilities.sql_runner import SqlRunner
from sql_agent.integrations.db.db_settings import DbSettings
from sql_agent.integrations.db.sql_validate import validate_sql

logger = logging.getLogger(__name__)

_MYSQL_IMPORT_ERROR: Optional[ImportError]
try:
    import pymysql
    from pymysql.cursors import Cursor
except ImportError as e:  # pragma: no cover
    pymysql = None  # type: ignore[assignment]
    Cursor = Any  # type: ignore[misc, assignment]
    _MYSQL_IMPORT_ERROR = e
else:
    _MYSQL_IMPORT_ERROR = None


class MySQLRunner(SqlRunner):
    """MySQL implementation of the SqlRunner interface."""

    def __init__(self, settings: DbSettings) -> None:
        if pymysql is None:
            raise ImportError(
                "未安装 pymysql，请 pip install pymysql。"
                f"原始错误: {_MYSQL_IMPORT_ERROR}"
            )
        self.settings = settings
        self.connection: Any = None

    def connect(self) -> Any:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                self.connection = pymysql.connect(
                    host=self.settings.db_host,
                    port=int(self.settings.db_port),
                    user=self.settings.db_user,
                    password=self.settings.db_password,
                    database=self.settings.db_database,
                    charset="utf8mb4",
                    autocommit=False,
                    cursorclass=Cursor,
                )
                logger.info(
                    "MySQL 连接成功: %s@%s:%s/%s",
                    self.settings.db_user,
                    self.settings.db_host,
                    self.settings.db_port,
                    self.settings.db_database,
                )
                return self.connection
            except Exception as e:
                last_error = e
                self.connection = None
                if attempt == 0:
                    continue
                raise ConnectionError(f"MySQL 连接失败: {e}") from e
        raise ConnectionError(f"MySQL 连接失败: {last_error}")

    def close(self) -> None:
        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass
            self.connection = None

    def reset_transaction(self) -> None:
        if self.connection is None:
            return
        try:
            self.connection.rollback()
        except Exception:
            pass

    def begin_readonly(self, cursor: Any) -> None:
        cursor.execute("START TRANSACTION READ ONLY")

    def is_alive(self) -> bool:
        if self.connection is None:
            return False
        try:
            self.connection.ping(reconnect=False)
            return True
        except Exception:
            return False
        finally:
            self.reset_transaction()

    def ensure_connection(self) -> None:
        if not self.is_alive():
            logger.warning("连接已断开，正在重连...")
            self.close()
            self.connect()

    def execute_readonly(self, sql: str) -> Tuple[List[str], List[tuple]]:
        if not validate_sql(sql):
            raise PermissionError("不安全的sql语句，拒绝执行")

        self.ensure_connection()
        self.reset_transaction()
        cursor = self.connection.cursor()
        try:
            self.begin_readonly(cursor)
            cleaned = sql.strip().rstrip(";").strip()
            cursor.execute(cleaned)
            columns = [col[0] for col in (cursor.description or [])]
            rows = cursor.fetchall() if cursor.description else []
            return columns, list(rows)
        finally:
            cursor.close()
            self.reset_transaction()

    def search_tables(self, keyword: str) -> List[dict]:
        self.ensure_connection()
        self.reset_transaction()
        cursor = self.connection.cursor()
        try:
            self.begin_readonly(cursor)
            safe = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{safe}%"
            cursor.execute(
                """
                SELECT TABLE_NAME, TABLE_SCHEMA, IFNULL(TABLE_COMMENT, '')
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_TYPE = 'BASE TABLE'
                  AND (TABLE_NAME LIKE %s OR TABLE_COMMENT LIKE %s)
                """,
                (pattern, pattern),
            )
            return [
                {
                    "table_name": r[0],
                    "schema_name": r[1],
                    "table_comment": r[2] or "",
                }
                for r in cursor.fetchall()
            ]
        finally:
            cursor.close()
            self.reset_transaction()

    def describe_table(self, table_name: str) -> List[dict]:
        self.ensure_connection()
        self.reset_transaction()
        cursor = self.connection.cursor()
        try:
            self.begin_readonly(cursor)
            cursor.execute(
                """
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE,
                       IFNULL(CHARACTER_MAXIMUM_LENGTH, 0),
                       IFNULL(COLUMN_COMMENT, '')
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
                """,
                (table_name,),
            )
            return [
                {
                    "column_name": r[0],
                    "data_type": r[1],
                    "is_nullable": str(r[2] or ""),
                    "data_length": int(r[3]) if r[3] is not None else 0,
                    "column_comment": r[4] or "",
                }
                for r in cursor.fetchall()
            ]
        finally:
            cursor.close()
            self.reset_transaction()

    def fetch_schema_metadata(self) -> Tuple[List[tuple], List[tuple]]:
        self.ensure_connection()
        return fetch_schema_metadata(self.connection)


def fetch_schema_metadata(raw_connection: Any) -> Tuple[List[tuple], List[tuple]]:
    """Pull full schema from MySQL and normalize to the same tuple format as DM."""
    cursor = raw_connection.cursor()
    try:
        cursor.execute(
            """
            SELECT TABLE_NAME, TABLE_SCHEMA, IFNULL(TABLE_COMMENT, '')
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
            """
        )
        tables = list(cursor.fetchall())

        cursor.execute(
            """
            SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE,
                   IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH,
                   IFNULL(COLUMN_COMMENT, '')
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
        )
        columns = list(cursor.fetchall())
        return tables, columns
    finally:
        cursor.close()
