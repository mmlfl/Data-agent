"""Aliyun's OpenAI-compatible dense embedding API."""

from __future__ import annotations

import math
from typing import Any

from openai import OpenAI

from sql_agent.capabilities.embedding.models import EncodedBatch, EncodedQuery
from sql_agent.capabilities.embedding.settings import EmbeddingSettings


class AliyunEmbedder:
    def __init__(self, settings: EmbeddingSettings, *, client: Any = None):
        self.settings = settings
        self._owns_client = client is None
        self._client = client if client is not None else OpenAI(
            api_key=settings.api_key.get_secret_value(), base_url=settings.base_url,
            timeout=settings.timeout_seconds, max_retries=2,
        )

    @property
    def dense_dim(self) -> int:
        return self.settings.dimensions

    @property
    def profile_id(self) -> str:
        return f"aliyun:{self.settings.model}:{self.dense_dim}"

    def validate_texts(self, texts: list[str]) -> None:
        for index, text in enumerate(texts):
            if not text.strip():
                raise ValueError(f"第 {index + 1} 条文档为空")
            # A conservative byte ceiling, not an inaccurate model tokenizer.
            # Reject oversized tables intact; never truncate or split a table.
            if len(text.encode("utf-8")) > self.settings.text_token_limit:
                raise ValueError(f"第 {index + 1} 条文档超过模型保守输入预算，请核对单表文本长度；未截断")

    def encode_documents(self, texts: list[str]) -> EncodedBatch:
        self.validate_texts(texts)
        vectors: list[list[float]] = []
        for offset in range(0, len(texts), self.settings.batch_size):
            batch = texts[offset:offset + self.settings.batch_size]
            response = self._client.embeddings.create(
                model=self.settings.model, input=batch,
                dimensions=self.dense_dim, encoding_format="float",
            )
            items = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in items] != list(range(len(batch))):
                raise ValueError("Embedding 返回数量或文档 index 不匹配")
            for item in items:
                vector = list(item.embedding)
                if len(vector) != self.dense_dim or not all(math.isfinite(v) for v in vector) or not any(vector):
                    raise ValueError("Embedding 返回了错误维度、非有限数值或零向量")
                vectors.append(vector)
        return EncodedBatch(dense=vectors)

    def encode_query(self, text: str) -> EncodedQuery:
        return EncodedQuery(dense=self.encode_documents([text]).dense[0])

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
