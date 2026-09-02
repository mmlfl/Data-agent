"""Read-only SQL validation — aligned with sql-agent/src/tools/tools.py."""

from __future__ import annotations

import re


def validate_sql(sql: str) -> bool:
    """只允许 SELECT；用正则词边界匹配，不误杀字段名。

    与 sql-agent 一致，并额外拒绝多语句（中间含分号），保证只读。
    """
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        return False

    sql_upper = cleaned.upper()
    if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
        return False

    # WITH ... SELECT 允许；WITH ... INSERT/UPDATE 等禁止（由 forbidden 捕获）
    forbidden = (
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|MERGE|REPLACE|"
        r"CALL|EXEC(UTE)?|GRANT|REVOKE|LOCK|UNLOCK|SET\s+ROLE)\b"
    )
    if re.search(forbidden, sql_upper):
        return False

    # 禁止多语句：去掉字符串字面量后再看是否还有分号
    without_literals = re.sub(r"('([^']|'')*')|(\"([^\"]|\"\")*\")", "", cleaned)
    if ";" in without_literals:
        return False

    return True
