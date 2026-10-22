import hashlib
import re

from sql_agent.capabilities.knoledge_store.models import (
    ApprovalStatus,
    KnowledgeKind,
    KnowledgeRecord,
)

_MAX_RECORD_ID_LEN = 128


def make_record_id(
    kind: KnowledgeKind | str,
    *,
    source_id: str,
) -> str:
    """生成稳定主键；过长则 SHA-256。"""
    kind_value = kind.value if isinstance(kind, KnowledgeKind) else str(kind)
    raw = f"{kind_value}:{source_id}"
    if len(raw) <= _MAX_RECORD_ID_LEN:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"hash:{digest}"


def content_hash_of(*parts: str) -> str:
    payload = "\n".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_SQL_STRING_LITERAL = re.compile(
    r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"",
    flags=re.DOTALL,
)
# 只认 FROM / JOIN 后的表引用；不扫 SELECT 列、WHERE 条件里的标识符
_FROM_JOIN_TABLE = re.compile(
    r"(?is)\b(?:FROM|JOIN)\s+"
    r"(?!\()"  # 跳过 FROM (subquery)
    r"([A-Za-z_][\w$#]*(?:\s*\.\s*[A-Za-z_][\w$#]*)?)"
)
_SQL_TABLE_STOPWORDS = {
    "SELECT",
    "WHERE",
    "SET",
    "VALUES",
    "DUAL",
}


def extract_sql_table_names(sql: str) -> list[str]:
    """从 SQL 抽出相关表名（FROM/JOIN），去重且保持出现顺序。

    不做全量标识符扫描——列名对关键词检索噪声大。
    """
    cleaned = _SQL_STRING_LITERAL.sub(" ", sql)
    found: list[str] = []
    seen: set[str] = set()
    for match in _FROM_JOIN_TABLE.finditer(cleaned):
        raw = re.sub(r"\s+", "", match.group(1))
        table = raw.split(".")[-1]
        key = table.upper()
        if key in _SQL_TABLE_STOPWORDS:
            continue
        if key not in seen:
            seen.add(key)
            found.append(table)
    return found


def extract_sql_identifiers(sql: str) -> list[str]:
    """兼容旧名：等价于 extract_sql_table_names（只返回表名）。"""
    return extract_sql_table_names(sql)


# 关键词：英标识符 或 连续中文（≥2 字）；不做整句粘贴
_LEXICAL_TOKEN = re.compile(r"[A-Za-z_][\w$#]*|[\u4e00-\u9fff]{2,}")
_LEXICAL_STOPWORDS = {
    "表",
    "说明",
    "字段",
    "的",
    "是",
    "和",
    "与",
    "及",
    "等",
    "为",
    "即",
    "或",
    "在",
    "有",
    "到",
    "从",
    "对",
    "把",
    "被",
    "让",
    "用",
    "这",
    "那",
    "一个",
    "我们",
    "可以",
    "进行",
    "相关",
    "主要包括",
    "VARCHAR",
    "VARCHAR2",
    "CHAR",
    "TEXT",
    "INT",
    "INTEGER",
    "BIGINT",
    "SMALLINT",
    "NUMBER",
    "NUMERIC",
    "DECIMAL",
    "FLOAT",
    "DOUBLE",
    "DATE",
    "TIME",
    "TIMESTAMP",
    "DATETIME",
    "BOOLEAN",
    "BOOL",
    "BLOB",
    "CLOB",
    "JSON",
}


def lexical_keywords(*texts: str, limit: int = 64) -> str:
    """从若干文本抽出关键词，去重保序；供 lexical_text 使用。"""
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in _LEXICAL_TOKEN.finditer(str(text)):
            token = match.group(0)
            key = token.upper() if token.isascii() else token
            if key in _LEXICAL_STOPWORDS or key in _SQL_TABLE_STOPWORDS:
                continue
            if len(token) == 1:
                continue
            if key not in seen:
                seen.add(key)
                found.append(token)
            if len(found) >= limit:
                return " ".join(found)
    return " ".join(found)


def build_question_sql_record(
    *,
    question: str,
    sql: str,
    source_id: str,
    source: str = "manual",
    approval_status: ApprovalStatus = ApprovalStatus.PENDING,
    active: bool = True,
    acl_groups: list[str] | None = None,
    metadata: dict | None = None,
) -> KnowledgeRecord:
    """从问句+SQL 构造一条 question_sql 知识。

    - dense_text：只用 question（语义检索）
    - lexical_text：只用表名关键词（稀疏/关键词检索，不含问句）
    - content：给 LLM 看的 Q + SQL
    """
    q = question.strip()
    s = sql.strip()
    tables = extract_sql_table_names(s)
    lexical = lexical_keywords(*tables)
    content = f"Q: {q}\nSQL: {s}"
    content_hash = content_hash_of(q, s)
    canonical_key = f"{KnowledgeKind.QUESTION_SQL.value}:{source_id}"
    record_id = make_record_id(
        KnowledgeKind.QUESTION_SQL,
        source_id=source_id,
    )
    meta = {
        "canonical_key": canonical_key,
        "content_hash": content_hash,
        "source_id": source_id,
        "tables": tables,
    }
    if metadata:
        meta.update(metadata)
    return KnowledgeRecord(
        kind=KnowledgeKind.QUESTION_SQL,
        dense_text=q,
        lexical_text=lexical,
        content=content,
        record_id=record_id,
        source=source,
        approval_status=approval_status,
        active=active,
        content_hash=content_hash,
        version=1,
        acl_groups=list(acl_groups or []),
        metadata=meta,
    )


def build_ddl_record(
    *,
    table_name: str,
    table_comment: str,
    columns: list[dict],
    source_id: str | None = None,
    source: str = "schema_cache",
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED,
    active: bool = True,
    acl_groups: list[str] | None = None,
    metadata: dict | None = None,
) -> KnowledgeRecord:
    """从表结构摘要构造 ddl 知识。

    - dense_text：人话表意（语义）
    - lexical_text：表名 + 列名 + 注释里的业务词（关键词检索，不含类型/整句说明）
    - content：给 LLM 看的表结构摘要
    """
    col_names: list[str] = []
    col_comments: list[str] = []
    comment_bits: list[str] = []
    for col in columns:
        name = str(col.get("name") or col.get("column_name") or "").strip()
        comment = str(col.get("comment") or col.get("column_comment") or "").strip()
        data_type = str(col.get("data_type") or "").strip()
        if not name:
            continue
        col_names.append(name)
        if comment:
            col_comments.append(comment)
        piece = name
        if data_type:
            piece += f" {data_type}"
        if comment:
            piece += f" ({comment})"
        comment_bits.append(piece)

    meaning = table_comment.strip() or table_name
    dense_text = f"表 {table_name}：{meaning}。关键字段：{'；'.join(comment_bits[:30])}"
    # 只要关键词：表名、列名、表/列注释中的词；不要整段 dense、不要类型名
    lexical_text = lexical_keywords(
        table_name,
        *col_names,
        table_comment,
        *col_comments,
    )
    lines = [
        f"表 {table_name}",
        f"说明: {meaning}",
        "字段:",
    ]
    for bit in comment_bits[:80]:
        lines.append(f"- {bit}")
    if len(comment_bits) > 80:
        lines.append(f"- ... 另有 {len(comment_bits) - 80} 列已省略")
    content = "\n".join(lines)

    sid = source_id or table_name
    content_hash = content_hash_of(table_name, meaning, "|".join(col_names))
    canonical_key = f"{KnowledgeKind.DDL.value}:{sid}"
    record_id = make_record_id(
        KnowledgeKind.DDL,
        source_id=sid,
    )
    meta = {
        "canonical_key": canonical_key,
        "content_hash": content_hash,
        "source_id": sid,
        "table_name": table_name,
    }
    if metadata:
        meta.update(metadata)
    return KnowledgeRecord(
        kind=KnowledgeKind.DDL,
        dense_text=dense_text,
        lexical_text=lexical_text,
        content=content,
        record_id=record_id,
        source=source,
        approval_status=approval_status,
        active=active,
        content_hash=content_hash,
        version=1,
        acl_groups=list(acl_groups or []),
        metadata=meta,
    )


def build_documentation_record(
    *,
    title: str,
    body: str,
    source_id: str,
    source: str = "manual",
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED,
    active: bool = True,
    acl_groups: list[str] | None = None,
    metadata: dict | None = None,
) -> KnowledgeRecord:
    """业务口径/说明文档。

    - dense_text / content：标题+正文（语义 / 给 LLM）
    - lexical_text：从标题与正文抽出的关键词（表名、业务词等），不是整段粘贴
    """
    title_s = title.strip()
    body_s = body.strip()
    dense_text = f"{title_s}\n{body_s}".strip()
    lexical_text = lexical_keywords(title_s, body_s)
    content = dense_text
    content_hash = content_hash_of(title_s, body_s)
    canonical_key = f"{KnowledgeKind.DOCUMENTATION.value}:{source_id}"
    record_id = make_record_id(
        KnowledgeKind.DOCUMENTATION,
        source_id=source_id,
    )
    meta = {
        "canonical_key": canonical_key,
        "content_hash": content_hash,
        "source_id": source_id,
        "title": title_s,
    }
    if metadata:
        meta.update(metadata)
    return KnowledgeRecord(
        kind=KnowledgeKind.DOCUMENTATION,
        dense_text=dense_text,
        lexical_text=lexical_text,
        content=content,
        record_id=record_id,
        source=source,
        approval_status=approval_status,
        active=active,
        content_hash=content_hash,
        version=1,
        acl_groups=list(acl_groups or []),
        metadata=meta,
    )
