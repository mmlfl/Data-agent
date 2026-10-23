"""One complete cached table is one searchable document, with no field slicing."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict

DOCUMENT_FORMAT = "single-table-v1"
TEXT_LIMITS = {
    "record_id": 128, "tenant_id": 128, "database_id": 128,
    "database_name": 1024, "dialect": 16, "schema_name": 1024,
    "table_name": 1024, "document_text": 65_535, "content_hash": 64,
}


class SchemaDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_id: str
    tenant_id: str
    database_id: str
    database_name: str
    dialect: str
    schema_name: str
    table_name: str
    document_text: str
    content_hash: str
    column_count: int
    active: bool = True

    def validate_storage(self) -> None:
        for key, maximum in TEXT_LIMITS.items():
            if len(getattr(self, key).encode("utf-8")) > maximum:
                raise ValueError(f"表 {self.table_name} 的 {key} 超过 {maximum} 字节；单表文档未截断")
        if not all((self.record_id, self.database_id.strip(), self.tenant_id.strip(), self.table_name.strip())):
            raise ValueError("表身份或数据源范围为空")
        if self.column_count <= 0:
            raise ValueError(f"表 {self.table_name} 缺少字段，请先刷新 SQLite 完整元数据")


def build_schema_document(
    table: dict[str, Any], *, database_id: str, tenant_id: str = "local",
    database_name: str = "", dialect: str = "dm",
) -> SchemaDocument:
    database_id, tenant_id = database_id.strip(), tenant_id.strip()
    table_name = str(table.get("table_name") or "").strip()
    schema_name = str(table.get("schema_name") or "").strip()
    columns = table.get("columns") or []
    identity = json.dumps([tenant_id, database_id, schema_name, table_name], ensure_ascii=False)
    record_id = "ddl:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    lines = [
        f"数据库标识：{database_id}", f"数据库名称：{database_name or database_id}",
        f"数据库类型：{dialect}", f"Schema：{schema_name or '未提供'}",
        f"表名：{table_name}", f"表说明：{table.get('table_comment') or '未提供'}",
        f"字段（共 {len(columns)} 个，以下为全部字段）：",
    ]
    for ordinal, column in enumerate(columns, 1):
        name = str(column.get("name") or column.get("column_name") or "").strip()
        if not name:
            raise ValueError(f"表 {table_name} 的第 {ordinal} 个字段没有名称")
        nullable = column.get("is_nullable")
        length = column.get("data_length")
        lines.append(
            f"{ordinal}. {name} | 类型：{column.get('data_type') or '未提供'}"
            f" | 长度：{length if length is not None else '未提供'}"
            f" | 可空：{nullable if nullable not in (None, '') else '未提供'}"
            f" | 注释：{column.get('comment') or column.get('column_comment') or '未提供'}"
        )
    text = "\n".join(lines)
    content_hash = hashlib.sha256((DOCUMENT_FORMAT + "\n" + text).encode("utf-8")).hexdigest()
    document = SchemaDocument(
        record_id=record_id, tenant_id=tenant_id, database_id=database_id,
        database_name=database_name or database_id, dialect=dialect, schema_name=schema_name,
        table_name=table_name, document_text=text, content_hash=content_hash, column_count=len(columns),
    )
    document.validate_storage()
    return document
