from typing import Literal
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    api_key: SecretStr = Field(validation_alias="DASHSCOPE_API_KEY")
    base_url: str = Field(validation_alias="DASHSCOPE_BASE_URL")
    model: str = Field(default="qwen3.7-text-embedding", validation_alias="EMBEDDING_MODEL")
    dimensions: Literal[64, 128, 256, 512, 768, 1024, 1536, 2048] = Field(default=1024, validation_alias="EMBEDDING_DIMENSIONS")
    batch_size: int = Field(default=10, ge=1, le=50, validation_alias="EMBEDDING_BATCH_SIZE")
    timeout_seconds: float = Field(default=30, gt=0, validation_alias="EMBEDDING_TIMEOUT_SECONDS")