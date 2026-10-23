from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MilvusSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    rag_enabled: bool = Field(default=False, validation_alias="RAG_ENABLED")

    milvus_uri: str = Field(default="", validation_alias="MILVUS_URI")
    milvus_database:str = Field(default="default", validation_alias="MILVUS_DATABASE")
    milvus_collection_name: str = Field(default="default_collection", validation_alias="MILVUS_COLLECTION")
    milvus_schema_collection: str = Field(
        default="sql_agent_schema_v1", min_length=1, validation_alias="MILVUS_SCHEMA_COLLECTION"
    )
    rag_database_id: str = Field(default="", validation_alias="RAG_DATABASE_ID")
    rag_database_name: str = Field(default="", validation_alias="RAG_DATABASE_NAME")
    rag_tenant_id: str = Field(default="local", validation_alias="RAG_TENANT_ID")
    milvus_memory_collection: str = Field(default="sql_agent_sql_memory_v1", min_length=1, validation_alias="MILVUS_MEMORY_COLLECTION")
    knowledge_db_path: str = Field(default="data/sql_agent_knowledge.db", validation_alias="SQL_AGENT_KNOWLEDGE_DB_PATH")
    milvus_connect_timeout_seconds: float= Field(
        default=30,
        gt=0,
        lt=300,
        validation_alias="MILVUS_CONNECT_TIMEOUT_SECONDS",
    )
    milvus_action_timeout_seconds: float= Field(
        default=60,
        gt=0,
        validation_alias="MILVUS_ACTION_TIMEOUT_SECONDS",
    )
    milvus_token: str = Field(default="", validation_alias="MILVUS_TOKEN")

    def require_uri(self) -> str:
        uri = self.milvus_uri.strip()
        if not uri:
            raise ValueError("MILVUS_URI 未配置，请填写 Milvus 地址")
        return uri
