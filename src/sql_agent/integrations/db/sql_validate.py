"""Read-only SQL validation — aligned with sql-agent/src/tools/tools.py."""

from __future__ import annotations

import re


def _strip_literals_and_comments(sql: str) -> str:
    without_comments = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    without_comments = re.sub(r"--[^\r\n]*|#[^\r\n]*", " ", without_comments)
    return re.sub(
        r"('([^']|'')*')|(\"([^\"]|\"\")*\")",
        " ",
        without_comments,
    )


def validate_sql(sql: str) -> bool:
    """只允许 SELECT；用正则词边界匹配，不误杀字段名。

    与 sql-agent 一致，并额外拒绝多语句（中间含分号），保证只读。
    """
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        return False

    safe_surface = _strip_literals_and_comments(cleaned)
    sql_upper = safe_surface.upper().strip()
    if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
        return False

    # WITH ... SELECT 允许；WITH ... INSERT/UPDATE 等禁止（由 forbidden 捕获）
    forbidden = (
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|MERGE|REPLACE|"
        r"CALL|EXEC(UTE)?|GRANT|REVOKE|LOCK|UNLOCK|SET\s+ROLE)\b"
    )
    if re.search(forbidden, sql_upper):
        return False

    dangerous_read_patterns = (
        r"\bINTO\s+(OUTFILE|DUMPFILE)\b|"
        r"\b(LOAD_FILE|SLEEP|BENCHMARK|GET_LOCK|RELEASE_LOCK)\s*\("
    )
    if re.search(dangerous_read_patterns, sql_upper):
        return False

    # 禁止多语句；字符串和注释中的分号不算语句分隔符。
    if ";" in safe_surface:
        return False

    return True
