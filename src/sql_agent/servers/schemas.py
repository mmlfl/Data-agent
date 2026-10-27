"""HTTP request/response models."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from sql_agent.components import UiComponent
from sql_agent.core.events import PROTOCOL_VERSION


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="User message")
    conversation_id: Optional[str] = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    run_id: Optional[str] = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class MetadataJobRequest(BaseModel):
    target: Literal["sqlite", "milvus", "knowledge"]


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "sql-agent"
    protocol_version: Literal["1"] = PROTOCOL_VERSION
    with_db: bool = False
    db_dialect: str = "-"
    tools: list[str] = Field(default_factory=list)
    cache_status: Optional[str] = None
    cache_table_count: int = 0


class CacheSyncResponse(BaseModel):
    status: str
    dialect: str
    table_count: int
    message: str = ""


class MilvusSyncResponse(BaseModel):
    status: str
    total: int
    written: int
    skipped: int = 0
    collection: str = ""
    message: str = ""


class CachedTable(BaseModel):
    table_name: str
    schema_name: str
    table_comment: str
    column_count: int
    synced_at: Optional[str] = None


class CacheTablesResponse(BaseModel):
    available: bool
    cache_file: str
    dialect: str
    total_tables: int
    total_columns: int
    last_synced_at: Optional[str] = None
    schemas: list[str]
    matched_tables: int
    offset: int
    limit: int
    tables: list[CachedTable]


class CachedColumn(BaseModel):
    column_name: str
    data_type: Optional[str] = None
    column_comment: Optional[str] = None
    is_nullable: Optional[str] = None
    data_length: Optional[int] = None


class CacheTableResponse(BaseModel):
    table_name: str
    schema_name: str
    table_comment: str
    synced_at: Optional[str] = None
    columns: list[CachedColumn]


class InspectionCheck(BaseModel):
    label: str
    ok: bool
    detail: str


class CacheCheckResponse(BaseModel):
    status: str
    message: str
    cache_file: str
    checks: list[InspectionCheck]


class MilvusDocumentSummary(BaseModel):
    record_id: str
    schema_name: str
    table_name: str
    column_count: int
    content_hash: str
    active: bool
    updated_at: Optional[str] = None
    comparison: str


class MilvusInspectionResponse(BaseModel):
    status: str
    message: str
    connected: bool
    rag_enabled: bool
    collection: str
    milvus_database: str
    database_id: str
    tenant_id: str
    collection_exists: Optional[bool] = None
    load_state: str
    can_browse: bool
    document_count: Optional[int] = None
    active_count: Optional[int] = None
    vector_dimensions: Optional[int] = None
    embedding_profile: Optional[str] = None
    configured_embedding_profile: str
    bm25: bool
    issues: list[str]
    indexes: list[Dict[str, Any]]
    matched_total: int
    browse_total: int
    truncated: bool
    scan_limit: int
    offset: int = 0
    limit: int = 30
    documents: list[MilvusDocumentSummary]
    checked_at: str


class MilvusStoredDocument(MilvusDocumentSummary):
    document_text: str
    database_name: str
    dialect: str
    content_hash_valid: bool


class MilvusDocumentResponse(MilvusInspectionResponse):
    document: Optional[MilvusStoredDocument] = None


class MilvusComparison(BaseModel):
    complete: bool
    scanned: int
    sqlite_tables: int
    matching: int
    stale: int
    sqlite_missing: int
    sqlite_incomplete: int
    inactive: int
    identity_mismatch: int
    duplicate_tables: int
    milvus_missing: Optional[int] = None
    consistent: bool


class MilvusCheckResponse(MilvusInspectionResponse):
    comparison: Optional[MilvusComparison] = None


class ToolsResponse(BaseModel):
    tools: list[str]


class QueryFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["satisfied", "unsatisfied"]


class AgentEventDTO(BaseModel):
    protocol_version: Literal["1"] = PROTOCOL_VERSION
    type: str
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    ui_component: Optional[UiComponent] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
