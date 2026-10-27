"""Database settings shared by SqlRunner integrations."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DbDialect = Literal["dm", "mysql"]


class DbSettings(BaseSettings):
    """Database connection + pool + schema cache settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    db_dialect: DbDialect = Field(default="dm", validation_alias="DB_DIALECT")
    db_host: str = Field(default="localhost", validation_alias="DB_HOST")
    db_port: int = Field(default=5236, validation_alias="DB_PORT")
    db_user: str = Field(default="", validation_alias="DB_USER")
    db_password: str = Field(default="", validation_alias="DB_PASSWORD")
    db_database: str = Field(default="", validation_alias="DB_DATABASE")
    db_pool_size: int = Field(default=5, validation_alias="DB_POOL_SIZE")
    db_max_result_rows: int = Field(
        default=100, gt=0, le=100, validation_alias="DB_MAX_RESULT_ROWS"
    )
    db_query_timeout_seconds: int = Field(
        default=30, gt=0, le=600, validation_alias="DB_QUERY_TIMEOUT_SECONDS"
    )
    schema_cache_path: Optional[str] = Field(
        default=None, validation_alias="SCHEMA_CACHE_PATH"
    )

    @field_validator("db_dialect", mode="before")
    @classmethod
    def _normalize_dialect(cls, value: object) -> str:
        key = str(value or "dm").strip().lower()
        if key in ("dameng", "达梦"):
            return "dm"
        if key not in ("dm", "mysql"):
            raise ValueError(f"DB_DIALECT 不支持: {value!r}（可选: dm, mysql）")
        return key

    def resolve_cache_path(self) -> Path:
        if self.schema_cache_path:
            return Path(self.schema_cache_path)
        # Local SQLite metadata cache (not a business DB — project extension vs Vanna)
        return Path(__file__).resolve().parents[4] / "data" / f"metadata_{self.db_dialect}_{self.source_fingerprint[:16]}.db"

    @property
    def source_fingerprint(self) -> str:
        return hashlib.sha256(json.dumps([self.db_dialect, self.db_host, self.db_port,
            self.db_database, self.db_user], ensure_ascii=False).encode()).hexdigest()

    def database_id(self, configured: str = "") -> str:
        if configured.strip():
            return configured.strip()
        from sql_agent.capabilities.knoledge_store.experience_models import stable_hash
        return "db:" + stable_hash([self.db_dialect, self.db_host, self.db_port,
                                   self.db_database, self.db_user])[:32]
