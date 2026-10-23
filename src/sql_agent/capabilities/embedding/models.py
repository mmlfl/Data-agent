"""Dense model output; BM25 sparse vectors are generated inside Milvus."""

from pydantic import BaseModel, Field


class EncodeQuery(BaseModel):
    dense: list[float]
    sparse: list[dict[str,float]] = Field(default_factory=list)

class EncodeBatch(BaseModel):
    dense: list[list[float]] = Field(default_factory=list)
    sparse:list[dict[str,float]] = Field(default_factory=list)


# Keep the existing names usable while exposing the names used by integrations.
EncodedQuery = EncodeQuery
EncodedBatch = EncodeBatch
