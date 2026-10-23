"""Store one complete table per entity; Milvus computes BM25 from document_text."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

from sql_agent.capabilities.embedding.base import Embedder
from sql_agent.capabilities.knoledge_store.schema_documents import SchemaDocument
from sql_agent.integrations.milvus.schema_collection import ensure_schema_collection


@dataclass
class SchemaSyncReport:
    total: int
    written: int = 0
    skipped: int = 0


class SchemaSyncError(RuntimeError):
    def __init__(self, report: SchemaSyncReport, record_ids: list[str], *, stage: str, cause_name: str):
        self.report = report
        self.record_ids = record_ids
        self.stage = stage
        super().__init__(
            f"单表同步在{stage}阶段失败（{cause_name}）：written={report.written}, "
            f"skipped={report.skipped}, total={report.total}；可重跑"
        )


class MilvusSchemaStore:
    """Injected resources are owned by the caller; this store never opens a connection."""

    def __init__(self, client: Any, *, embedder: Embedder, collection_name: str,
                 timeout: float = 60, batch_size: int = 10):
        if timeout <= 0 or batch_size <= 0:
            raise ValueError("timeout 和 batch_size 必须为正数")
        self.client = client
        self.embedder = embedder
        self.collection_name = collection_name
        self.timeout = timeout
        self.batch_size = batch_size

    def ensure(self) -> None:
        ensure_schema_collection(self.client, name=self.collection_name,
                                 embedder=self.embedder, timeout=self.timeout)

    def upsert(self, documents: list[SchemaDocument], *, force: bool = False) -> SchemaSyncReport:
        report = SchemaSyncReport(total=len(documents))
        if len({doc.record_id for doc in documents}) != len(documents):
            raise ValueError("输入中存在重复的单表文档 ID")
        for document in documents:
            document.validate_storage()
        self.embedder.validate_texts([doc.document_text for doc in documents])
        if not documents:
            return report
        self.ensure()
        for offset in range(0, len(documents), self.batch_size):
            batch = documents[offset:offset + self.batch_size]
            stage = "读取已有记录"
            try:
                # Stable IDs contain source scope. No ANN lookup is used for deduplication.
                previous = self.client.query(
                    collection_name=self.collection_name,
                    filter="record_id in {ids}", filter_params={"ids": [doc.record_id for doc in batch]},
                    output_fields=["record_id", "content_hash", "active"],
                    consistency_level="Strong", timeout=self.timeout,
                )
                old = {row["record_id"]: row for row in previous}
                changed = [doc for doc in batch if force or not (
                    doc.record_id in old and old[doc.record_id]["content_hash"] == doc.content_hash
                    and old[doc.record_id]["active"] == doc.active
                )]
                report.skipped += len(batch) - len(changed)
                if not changed:
                    continue
                stage = "Embedding"
                encoded = self.embedder.encode_documents([doc.document_text for doc in changed])
                entities = []
                for doc, vector in zip(changed, encoded.dense, strict=True):
                    if len(vector) != self.embedder.dense_dim or not all(math.isfinite(v) for v in vector) or not any(vector):
                        raise ValueError("不能将非法向量写入 Milvus")
                    row = doc.model_dump()
                    # sparse_vector is a BM25 function output, never supplied by the client.
                    row.update(dense_vector=vector, updated_at=int(time.time()))
                    entities.append(row)
                stage = "Milvus 写入"
                result = self.client.upsert(collection_name=self.collection_name, data=entities, timeout=self.timeout)
                written = int(result.get("upsert_count", 0))
                if written != len(entities):
                    raise RuntimeError("Milvus 返回的写入数量与单表文档数量不符")
                report.written += written
            except Exception as error:
                raise SchemaSyncError(report, [doc.record_id for doc in batch],
                                      stage=stage, cause_name=type(error).__name__) from error
        return report

    def get_document(self, record_id: str, *, database_id: str, tenant_id: str = "local") -> dict | None:
        """Read stored text for inspection or future retrieval output, within source scope."""
        if not all(value.strip() for value in (record_id, database_id, tenant_id)):
            raise ValueError("查询必须提供记录与数据源范围")
        self.ensure()
        rows = self.client.query(
            collection_name=self.collection_name,
            filter="record_id == {id} and database_id == {database} and tenant_id == {tenant} and active == true",
            filter_params={"id": record_id, "database": database_id, "tenant": tenant_id},
            output_fields=["record_id", "database_id", "database_name", "tenant_id", "dialect",
                           "schema_name", "table_name", "document_text", "column_count", "content_hash", "updated_at"],
            consistency_level="Strong", timeout=self.timeout,
        )
        return rows[0] if rows else None
