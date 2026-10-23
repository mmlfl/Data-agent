"""Embedding capability, independent of provider and vector database."""

from typing import Protocol

from sql_agent.capabilities.embedding.models import EncodedBatch, EncodedQuery


class Embedder(Protocol):
    @property
    def dense_dim(self) -> int: ...

    @property
    def profile_id(self) -> str: ...

    def validate_texts(self, texts: list[str]) -> None: ...

    def encode_documents(self, texts: list[str]) -> EncodedBatch: ...

    def encode_query(self, text: str) -> EncodedQuery: ...

    def close(self) -> None: ...
