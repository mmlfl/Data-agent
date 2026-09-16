"""Dameng (DM) SqlRunner — 对齐 sql-agent/src/db/dameng.py 的只读连接与事务策略。"""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any, List, Optional, Tuple

from sql_agent.capabilities.sql_runner import SqlExecutionResult, SqlRunner
from sql_agent.integrations.db.db_settings import DbSettings
from sql_agent.integrations.db.sql_validate import validate_sql

logger = logging.getLogger(__name__)

# 必须在 import dmPython 之前设置 DM_HOME
# DPI 通过 DM_HOME/bin/ 查找加密模块（libeay32.dll / ssleay32.dll），
# 不设置会导致 [CODE:-70089] 加密模块加载失败（与 sql-agent 相同处理）
if "DM_HOME" not in os.environ:
    import sysconfig

    _site_packages = sysconfig.get_paths()["purelib"]
    _dm_home = os.path.join(_site_packages, "dm_home")
    _bin_dir = os.path.join(_dm_home, "bin")
    if not os.path.isdir(_bin_dir):
        os.makedirs(_bin_dir, exist_ok=True)
        for _f in os.listdir(_site_packages):
            if _f.endswith(".dll"):
                _src = os.path.join(_site_packages, _f)
                _dst = os.path.join(_bin_dir, _f)
                if not os.path.exists(_dst):
                    shutil.copy2(_src, _dst)
    os.environ["DM_HOME"] = _dm_home
    if _bin_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _bin_dir + os.pathsep + os.environ.get("PATH", "")

_DM_IMPORT_ERROR: Optional[ImportError]
try:
    import dmPython
except ImportError as e:  # pragma: no cover
    dmPython = None  # type: ignore[assignment]
    _DM_IMPORT_ERROR = e
else:
    _DM_IMPORT_ERROR = None


class DamengRunner(SqlRunner):
    """达梦 SqlRunner：连接策略与只读事务对齐 sql-agent DamengDB。"""

    def __init__(self, settings: DbSettings) -> None:
        if dmPython is None:
            raise ImportError(
                "未安装 dmPython，无法使用达梦方言。请 pip/uv 安装 dmpython，"
                f"或将 DB_DIALECT 改为 mysql。原始错误: {_DM_IMPORT_ERROR}"
            )
        self.settings = settings
        self.connection: Any = None

    def connect(self) -> Any:
        """连接达梦（首次可能因 DPI 初始化延迟失败，重试一次）。"""
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                self.connection = dmPython.connect(
                    user=self.settings.db_user,
                    password=self.settings.db_password,
                    host=self.settings.db_host,
                    port=self.settings.db_port,
                )
                # 与 sql-agent 一致：关闭自动提交，由只读事务显式控制
                self.connection.autocommit = False
                logger.info(
                    "达梦连接成功: %s@%s:%s",
                    self.settings.db_user,
                    self.settings.db_host,
                    self.settings.db_port,
                )
                return self.connection
            except SystemError as e:
                last_error = e
                self.connection = None
                if attempt == 0:
                    continue
                raise ConnectionError(f"达梦连接失败: {e}") from e
        raise ConnectionError(f"达梦连接失败: {last_error}")

    def close(self) -> None:
        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass
            self.connection = None

    def reset_transaction(self) -> None:
        """归还连接池前清理事务状态（与 sql-agent pool.put 一致）。"""
        if self.connection is None:
            return
        try:
            self.connection.rollback()
        except Exception:
            pass

    def begin_readonly(self, cursor: Any) -> None:
        """达梦只读事务：SET TRANSACTION READ ONLY。"""
        cursor.execute("SET TRANSACTION READ ONLY")

    def is_alive(self) -> bool:
        if self.connection is None:
            return False
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.close()
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

    def execute_readonly(
        self, sql: str, *, max_rows: int
    ) -> SqlExecutionResult:
        """对齐 sql-agent tools._execute_sql：校验 → 只读事务 → 执行。"""
        if not validate_sql(sql):
            raise PermissionError("不安全的sql语句，拒绝执行")
        if max_rows <= 0:
            raise ValueError("max_rows must be positive")

        self.ensure_connection()
        self.reset_transaction()
        cursor = self.connection.cursor()
        try:
            self.begin_readonly(cursor)
            cleaned = sql.strip().rstrip(";").strip()
            cursor.execute(cleaned)
            columns = [col[0] for col in (cursor.description or [])]
            fetched = (
                list(cursor.fetchmany(max_rows + 1)) if cursor.description else []
            )
            return SqlExecutionResult(
                columns=columns,
                rows=fetched[:max_rows],
                truncated=len(fetched) > max_rows,
            )
        finally:
            cursor.close()
            self.reset_transaction()

    def search_tables(self, keyword: str) -> List[dict]:
        """回源搜索表（只读事务内查询系统视图）。"""
        self.ensure_connection()
        self.reset_transaction()
        cursor = self.connection.cursor()
        try:
            self.begin_readonly(cursor)
            safe = keyword.replace("'", "''")
            pattern = f"%{safe}%"
            cursor.execute(
                f"""
                SELECT TABLE_NAME, OWNER, COMMENTS
                FROM ALL_TAB_COMMENTS
                WHERE OWNER = USER
                  AND TABLE_NAME NOT LIKE 'SYS%'
                  AND TABLE_NAME NOT LIKE 'DM%'
                  AND TABLE_NAME NOT LIKE 'V$%'
                  AND (TABLE_NAME LIKE '{pattern}' OR COMMENTS LIKE '{pattern}')
                """
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
        """回源描述表结构（只读事务）。"""
        self.ensure_connection()
        self.reset_transaction()
        cursor = self.connection.cursor()
        try:
            self.begin_readonly(cursor)
            safe_name = table_name.replace("'", "''")
            cursor.execute(
                f"""
                SELECT c.COLUMN_NAME, c.DATA_TYPE, c.NULLABLE, c.DATA_LENGTH,
                       NVL(cc.COMMENTS, '') AS COLUMN_COMMENT
                FROM ALL_TAB_COLUMNS c
                LEFT JOIN ALL_COL_COMMENTS cc
                  ON cc.OWNER = c.OWNER
                 AND cc.TABLE_NAME = c.TABLE_NAME
                 AND cc.COLUMN_NAME = c.COLUMN_NAME
                WHERE c.OWNER = USER
                  AND UPPER(c.TABLE_NAME) = UPPER('{safe_name}')
                ORDER BY c.COLUMN_ID
                """
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
        """全量元数据同步：在只读事务内拉取（保证只读）。"""
        self.ensure_connection()
        self.reset_transaction()
        cursor = self.connection.cursor()
        try:
            self.begin_readonly(cursor)
            return _fetch_schema_metadata_on_cursor(cursor)
        finally:
            cursor.close()
            self.reset_transaction()


def fetch_schema_metadata(raw_connection: Any) -> Tuple[List[tuple], List[tuple]]:
    """兼容旧调用：直接在原始连接上拉元数据（调用方应自行只读）。"""
    cursor = raw_connection.cursor()
    try:
        return _fetch_schema_metadata_on_cursor(cursor)
    finally:
        cursor.close()


def _fetch_schema_metadata_on_cursor(cursor: Any) -> Tuple[List[tuple], List[tuple]]:
    """从达梦拉取元数据，归一化格式与 sql-agent 一致。"""
    cursor.execute(
        """
        SELECT TABLE_NAME, OWNER, COMMENTS
        FROM ALL_TAB_COMMENTS
        WHERE OWNER = USER
          AND TABLE_NAME NOT LIKE 'SYS%'
          AND TABLE_NAME NOT LIKE 'DM%'
          AND TABLE_NAME NOT LIKE 'V$%'
        """
    )
    tables = list(cursor.fetchall())

    cursor.execute(
        """
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE,
               NULLABLE, DATA_LENGTH
        FROM ALL_TAB_COLUMNS
        WHERE OWNER = USER
        ORDER BY TABLE_NAME, COLUMN_ID
        """
    )
    all_columns = cursor.fetchall()

    cursor.execute(
        """
        SELECT TABLE_NAME, COLUMN_NAME, COMMENTS
        FROM ALL_COL_COMMENTS
        WHERE OWNER = USER
        """
    )
    comment_map = {(r[0], r[1]): r[2] for r in cursor.fetchall()}

    columns: List[tuple] = []
    for col in all_columns:
        table_name, col_name, data_type, nullable, data_len = col
        columns.append(
            (
                table_name,
                col_name,
                data_type,
                nullable,
                data_len,
                comment_map.get((table_name, col_name), "") or "",
            )
        )
    return tables, columns
