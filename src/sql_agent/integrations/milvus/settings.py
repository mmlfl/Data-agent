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
    milvus_connect_timeout_seconds: float= Field(
        default=30,
        gt=0,
        lt=300,
        validation_alias="MILVUS_CONNECT_TIMEOUT_SECONDS",
    )
    milvus_action_timeout_seconds: float= Field(
        default=60,
        validation_alias="MILVUS_ACTION_TIMEOUT_SECONDS",
    )
    milvus_token: str = Field(default="", validation_alias="MILVUS_TOKEN")

    def require_uri(self) -> str:
        uri = self.milvus_uri.strip()
        if not uri:
            raise ValueError("MILVUS_URI 未配置，请填写 Milvus 地址")
        return uri
