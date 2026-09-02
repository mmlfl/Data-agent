"""Database settings shared by SqlRunner integrations."""

from __future__ import annotations

from pathlib import Path
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
        return Path(__file__).resolve().parent / f"metadata_{self.db_dialect}.db"
