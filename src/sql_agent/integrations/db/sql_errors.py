"""Classify driver diagnostics without retrying deterministic SQL mistakes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SqlError:
    code: str
    hint: str
    retryable: bool = False
    repairable: bool = True


def classify_sql_error(error, dialect=None):
    text = str(error).lower()
    number = error.args[0] if error.args else None
    if isinstance(error, TimeoutError) or number in (3024, 1969, 1205) or any(
            word in text for word in ("timeout", "timed out", "超时")):
        return SqlError("sql_query_timeout", "缩小时间/数据范围或简化查询，不要立即重跑同一 SQL。")
    if isinstance(error, PermissionError) or number in (1044, 1045, 1142, 1143) or any(
            word in text for word in ("permission denied", "access denied", "权限不足", "没有权限")):
        return SqlError("sql_permission_denied", "当前账号无访问权限，请说明限制，不要重复执行或尝试绕过权限。", repairable=False)
    if number in (1054, 1052) or any(word in text for word in (
            "unknown column", "invalid column", "ambiguous column", "无效的列", "列名无效", "不明确的列", "列不存在")):
        return SqlError("sql_column_error", "调用 describe_table 核对字段，补全别名或改用真实字段；若缓存与报错矛盾，设 refresh=true 回源刷新当前表再修正。")
    if number == 1146 or any(word in text for word in ("doesn't exist", "invalid table", "无效的表", "表不存在")):
        return SqlError("sql_table_error", "用 list_tables/search_schema 确认真实表名和 schema，再修正 SQL。")
    if number in (1064, 1055, 1140) or any(word in text for word in ("syntax", "group by", "语法", "分组")):
        return SqlError("sql_syntax_error", "根据当前数据库方言修正语法或 GROUP BY，保留原业务口径。")
    # Only known connection failures get one transparent retry. Unknown errors
    # must surface rather than executing the same expensive SQL twice.
    if isinstance(error, ConnectionError) or number in (2002, 2003, 2006, 2013) or any(
            word in text for word in ("connection reset", "connection refused", "connection closed", "连接已关闭", "连接断开")):
        return SqlError("sql_connection_error", "临时连接故障；系统最多原样重试一次，仍失败请稍后重试。", True, False)
    return SqlError("sql_execution_failed", "核对错误与相关结构后决定是否修正；不要无依据重复相同 SQL。")
