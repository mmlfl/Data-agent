"""Explicit SQLite-to-Milvus synchronization; no resources are created at import time."""

from pathlib import Path

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
