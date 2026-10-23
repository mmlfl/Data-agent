from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )
    api_key: SecretStr = Field(validation_alias="DASHSCOPE_API_KEY")
    base_url: str = Field(validation_alias="DASHSCOPE_BASE_URL")
    model: Literal["qwen3.7-text-embedding", "qwen3.7-text-embedding-flash", "text-embedding-v4"] = Field(default="qwen3.7-text-embedding", validation_alias="EMBEDDING_MODEL")
    dimensions: int = Field(default=1024, gt=0, validation_alias="EMBEDDING_DIMENSIONS")
    batch_size: int = Field(default=10, ge=1, le=20, validation_alias="EMBEDDING_BATCH_SIZE")
    timeout_seconds: float = Field(default=30, gt=0, validation_alias="EMBEDDING_TIMEOUT_SECONDS")

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or any(c in value for c in "<>{}"):
            raise ValueError("DASHSCOPE_BASE_URL 必须是控制台提供的完整 HTTPS 地址")
        return value

    @model_validator(mode="after")
    def validate_model_limits(self):
        if not self.api_key.get_secret_value().strip():
            raise ValueError("DASHSCOPE_API_KEY 未配置")
        dimensions = {256, 512, 768, 1024}
        if self.model != "qwen3.7-text-embedding-flash":
            dimensions |= {1536, 2048}
        if self.model == "qwen3.7-text-embedding":
            dimensions.add(2560)
        if self.model == "text-embedding-v4":
            dimensions |= {64, 128}
            if self.batch_size > 10:
                raise ValueError("text-embedding-v4 每批最多 10 条")
        if self.dimensions not in dimensions:
            raise ValueError(f"{self.model} 不支持该向量维度")
        return self

    @property
    def text_token_limit(self) -> int:
        return 8192 if self.model == "text-embedding-v4" else 128_000
