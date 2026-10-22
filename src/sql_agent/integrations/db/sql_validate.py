"""Parse, inspect and bound SQL before it can reach a database driver."""

from __future__ import annotations

import os

import sqlglot
from sqlglot import ErrorLevel, exp
from sqlglot.errors import SqlglotError
from sql_agent.capabilities.sql_runner.models import MAX_QUERY_ROWS

MAX_SQL_LENGTH = 100_000


class SqlValidationError(PermissionError):
    """A query cannot be proven safe by the configured AST policy."""


# SQLGlot's canonical function names, not substrings of the input text.
# Unknown/UDF/package functions require review before being added.
_READ_FUNCTIONS = frozenset("""
    ABS AVG COUNT MAX MIN SUM ROUND FLOOR CEIL CEILING MOD POWER SQRT SIGN
    COALESCE NULLIF IF CASE CAST TRY_CAST CONVERT EXTRACT
    LENGTH CHAR_LENGTH CHARACTER_LENGTH OCTET_LENGTH LOWER UPPER INITCAP
    TRIM LTRIM RTRIM SUBSTRING LEFT RIGHT REPLACE CONCAT CONCAT_WS
    STR_POSITION INSTR LOCATE LPAD RPAD REPEAT REVERSE SPLIT_PART
    DATE DATETIME TIMESTAMP DATE_ADD DATE_SUB DATE_DIFF DATEDIFF
    DATE_TRUNC TIMESTAMP_ADD TIMESTAMP_SUB TIMESTAMP_DIFF TIMESTAMP_TRUNC
    CURRENT_DATE CURRENT_TIME CURRENT_TIMESTAMP LOCALTIME LOCALTIMESTAMP
    YEAR MONTH DAY DAY_OF_MONTH DAY_OF_WEEK DAY_OF_YEAR HOUR MINUTE SECOND
    TIME_TO_STR STR_TO_TIME STR_TO_DATE STR_TO_TIMESTAMP TO_CHAR TO_DATE TO_NUMBER
    TS_OR_DS_TO_DATE TS_OR_DS_TO_TIMESTAMP LAST_DAY ADD_MONTHS MONTHS_BETWEEN TRUNC
    UNIX_TIMESTAMP UNIX_TO_TIME TIME_TO_UNIX
    ROW_NUMBER RANK DENSE_RANK PERCENT_RANK CUME_DIST NTILE
    LAG LEAD FIRST_VALUE LAST_VALUE NTH_VALUE
    STDDEV STDDEV_POP STDDEV_SAMP VARIANCE VAR_POP VAR_SAMP
    GROUP_CONCAT LISTAGG ARRAY_AGG STRING_AGG
    JSON_EXTRACT JSON_EXTRACT_SCALAR JSON_UNQUOTE JSON_LENGTH
    JSON_VALUE JSON_QUERY JSON_ARRAYAGG JSON_OBJECTAGG
    REGEXP_LIKE REGEXP_REPLACE REGEXP_EXTRACT REGEXP_INSTR REGEXP_COUNT
    GREATEST LEAST DATE_FORMAT NVL NVL2 DECODE
""".split())

_FORBIDDEN_NODES = (
    exp.DML, exp.DDL, exp.Command, exp.Into, exp.Lock, exp.Hint,
    exp.PropertyEQ, exp.Parameter, exp.SessionParameter, exp.NextValueFor,
)


def sql_dialect(dialect: str | None = None) -> str:
    """DM queries use the Oracle-compatible parser/generator, not MySQL."""
    value = (dialect or os.getenv("DB_DIALECT", "dm")).lower().strip()
    if value in {"dm", "dameng", "oracle", "达梦"}:
        return "oracle"
    if value == "mysql":
        return "mysql"
    raise SqlValidationError("不支持的 SQL 方言")


def _parse_readonly(sql: str, dialect: str) -> exp.Select:
    if not sql.strip() or len(sql) > MAX_SQL_LENGTH:
        raise SqlValidationError("SQL 为空或超过长度限制")
    try:
        statements = sqlglot.parse(sql, read=dialect, error_level=ErrorLevel.RAISE)
    except (SqlglotError, RecursionError, ValueError) as error:
        raise SqlValidationError("SQL 解析失败，请检查语法与数据库方言") from error
    # Do not discard None nodes: extra delimiters must not hide statements.
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise SqlValidationError("仅允许一条 SELECT 查询（可包含只读 CTE 和子查询）")
    query = statements[0]
    for index, node in enumerate(query.walk()):
        if index >= 10_000:
            raise SqlValidationError("SQL 结构过于复杂")
        if isinstance(node, _FORBIDDEN_NODES):
            raise SqlValidationError("SQL 包含写操作、锁定、变量赋值、提示或其他非只读结构")
        if isinstance(node, exp.Select) and node.args.get("operation_modifiers"):
            raise SqlValidationError("不允许 SELECT 执行修饰符")
        if isinstance(node, exp.Column) and node.name.upper() in {"NEXTVAL", "CURRVAL"}:
            raise SqlValidationError("不允许访问数据库序列")
        if isinstance(node, exp.Dot) and node.find(exp.Func) is not None:
            raise SqlValidationError("不允许调用数据库包或带命名空间的函数")
        if isinstance(node, exp.Func):
            name = node.name.upper() if isinstance(node, exp.Anonymous) else node.sql_name()
            if name not in _READ_FUNCTIONS:
                raise SqlValidationError(f"不允许调用未审核的 SQL 函数：{name}")
    return query


def validate_sql(sql: str, *, dialect: str | None = None) -> bool:
    """Compatibility predicate; runners execute prepare_readonly_sql's output."""
    try:
        prepare_readonly_sql(sql, dialect=dialect)
    except SqlValidationError:
        return False
    return True


def prepare_readonly_sql(
    sql: str, *, dialect: str | None = None, max_rows: int = MAX_QUERY_ROWS
) -> str:
    """Return validated SQL with a database-side cap and no input comments.

    MySQL emits LIMIT; DM/Oracle emits FETCH FIRST ... ROWS ONLY. Existing
    smaller limits and offsets are preserved. Never execute the original text:
    regenerating the AST also removes MySQL executable comments.
    """
    if max_rows <= 0:
        raise ValueError("max_rows must be positive")
    row_cap = min(max_rows, MAX_QUERY_ROWS)
    target_dialect = sql_dialect(dialect)
    try:
        query = _parse_readonly(sql, target_dialect)
        limit = query.args.get("limit")
        if limit is not None:
            options = limit.args.get("limit_options")
            if options and (options.args.get("percent") or options.args.get("with_ties")):
                raise SqlValidationError("不允许百分比或 WITH TIES 限行")
            count = limit.args.get("expression") or limit.args.get("count")
            if not isinstance(count, exp.Literal) or not count.is_int or int(count.this) < 0:
                raise SqlValidationError("行数限制必须是非负整数字面量")
            row_cap = min(row_cap, int(count.this))
        query = query.limit(row_cap, copy=False)
        return query.sql(dialect=target_dialect, comments=False, unsupported_level=ErrorLevel.RAISE)
    except SqlValidationError:
        raise
    except (SqlglotError, RecursionError, ValueError) as error:
        raise SqlValidationError("无法安全生成该方言的 SQL") from error
