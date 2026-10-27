"""Explicit SQLite-to-Milvus synchronization; no resources are created at import time."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from sql_agent.capabilities.knoledge_store.schema_documents import SchemaDocument, build_schema_document
from sql_agent.integrations.db.schema_cache import read_cached_schema_documents
from sql_agent.integrations.milvus.schema_store import MilvusSchemaStore, SchemaSyncReport


def load_schema_documents(
    cache_path: str | Path, *, database_id: str, database_name: str = "", tenant_id: str = "local",
    dialect: str = "dm", table_names: list[str] | None = None,
) -> list[SchemaDocument]:
    tables = read_cached_schema_documents(cache_path, table_names=table_names)
    return [build_schema_document(table, database_id=database_id, database_name=database_name,
                                  tenant_id=tenant_id, dialect=dialect) for table in tables]


def sync_cached_schema(cache_path: str | Path, store: MilvusSchemaStore, *, database_id: str,
                       database_name: str = "", tenant_id: str = "local", dialect: str = "dm",
                       table_names: list[str] | None = None, force: bool = False) -> SchemaSyncReport:
    documents = load_schema_documents(cache_path, database_id=database_id, database_name=database_name,
                                     tenant_id=tenant_id, dialect=dialect, table_names=table_names)
    return store.upsert(documents, force=force)


def execute_schema_sync(
    *,
    cache_path: str | Path | None = None,
    database_id: str | None = None,
    database_name: str | None = None,
    tenant_id: str | None = None,
    collection: str | None = None,
    table_names: list[str] | None = None,
    refresh_cache: bool = False,
    dry_run: bool = False,
    force: bool = False,
    progress=None,
) -> dict[str, Any]:
    """Load SQLite-cached table docs and upsert them into the schema collection."""
    from contextlib import ExitStack

    from sql_agent.capabilities.embedding.settings import EmbeddingSettings
    from sql_agent.integrations.db import DbSettings, SchemaCache, create_sql_runner_pool
    from sql_agent.integrations.embedding.aliyun import AliyunEmbedder
    from sql_agent.integrations.milvus.client import create_milvus_client
    from sql_agent.integrations.milvus.settings import MilvusSettings

    if dry_run and refresh_cache:
        raise ValueError("--dry-run 只读取本地缓存，不能同时使用 --refresh-cache")

    db_settings = DbSettings()
    milvus_settings = MilvusSettings()
    resolved_database_id = db_settings.database_id(database_id if database_id is not None else milvus_settings.rag_database_id)
    resolved_tenant_id = tenant_id if tenant_id is not None else milvus_settings.rag_tenant_id
    if not resolved_database_id.strip() or not resolved_tenant_id.strip():
        raise ValueError("请设置 RAG_DATABASE_ID / RAG_TENANT_ID")

    resolved_cache_path = Path(cache_path) if cache_path else db_settings.resolve_cache_path()
    name = collection or milvus_settings.milvus_schema_collection
    resolved_database_name = (
        database_name if database_name is not None else milvus_settings.rag_database_name
    )

    if refresh_cache:
        pool = create_sql_runner_pool(db_settings)
        try:
            SchemaCache(pool, settings=db_settings, db_path=resolved_cache_path).sync()
        finally:
            pool.close()

    documents = load_schema_documents(
        resolved_cache_path,
        database_id=resolved_database_id,
        tenant_id=resolved_tenant_id,
        database_name=resolved_database_name,
        dialect=db_settings.db_dialect,
        table_names=table_names,
    )
    if dry_run:
        return {
            "dry_run": True,
            "status": "ok",
            "collection": name,
            "total": len(documents),
            "written": 0,
            "skipped": 0,
            "documents": len(documents),
            "columns": sum(doc.column_count for doc in documents),
            "largest_document_bytes": max(
                (len(doc.document_text.encode("utf-8")) for doc in documents), default=0
            ),
            "preview_tables": [doc.table_name for doc in documents[:10]],
        }
    if not documents:
        return {"status": "success", "total": 0, "written": 0, "skipped": 0, "collection": name}

    milvus_settings.require_uri()
    settings = EmbeddingSettings()
    with ExitStack() as resources:
        embedder = AliyunEmbedder(settings)
        resources.callback(embedder.close)
        embedder.validate_texts([doc.document_text for doc in documents])
        client = create_milvus_client(milvus_settings)
        resources.callback(client.close)
        store = MilvusSchemaStore(
            client,
            embedder=embedder,
            collection_name=name,
            timeout=milvus_settings.milvus_action_timeout_seconds,
            batch_size=settings.batch_size,
            progress=progress,
        )
        report = store.upsert(documents, force=force, full_snapshot=table_names is None)
        return {
            **asdict(report),
            "status": "success",
            "collection": name,
            "embedding_profile": embedder.profile_id,
        }
