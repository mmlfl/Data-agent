from __future__ import annotations

import re

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MILVUS_DB_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,254}$")


class MilvusSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    rag_enabled: bool = Field(default=False, validation_alias="RAG_ENABLED")

    milvus_uri: str = Field(default="", validation_alias="MILVUS_URI")
    # Attu 左侧「数据库」。MILVUS_DATEBASE 是常见拼写，二者都表示这个库，不是 entity.database_name。
    milvus_database: str = Field(
        default="default",
        validation_alias=AliasChoices("MILVUS_DATABASE", "MILVUS_DATEBASE"),
    )
    milvus_collection_name: str = Field(default="sql_agent_schema_v1", validation_alias="MILVUS_COLLECTION")
    milvus_schema_collection: str = Field(default="", validation_alias="MILVUS_SCHEMA_COLLECTION")
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

    @field_validator("milvus_database", mode="before")
    @classmethod
    def default_database(cls, value: object) -> str:
        text = str(value or "").strip() or "default"
        if not _MILVUS_DB_NAME_RE.match(text):
            raise ValueError(
                "MILVUS_DATABASE 是 Attu 左侧的 Milvus 数据库名，只能字母/数字/下划线，空则 default。"
                "记录字段 database_name 请用 RAG_DATABASE_NAME（可以中文）。"
            )
        return text

    @model_validator(mode="after")
    def default_schema_collection(self) -> "MilvusSettings":
        schema = self.milvus_schema_collection.strip()
        collection = self.milvus_collection_name.strip() or "sql_agent_schema_v1"
        if not collection:
            collection = "sql_agent_schema_v1"
        self.milvus_collection_name = collection
        self.milvus_schema_collection = schema or collection
        return self

    def require_uri(self) -> str:
        uri = self.milvus_uri.strip()
        if not uri:
            raise ValueError("MILVUS_URI 未配置，请填写 Milvus 地址")
        return uri
