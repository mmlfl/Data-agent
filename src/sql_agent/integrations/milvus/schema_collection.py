"""Production single-table schema: dense + server-generated BM25, separate from labs."""

from __future__ import annotations

import json
from typing import Any

from pymilvus import DataType, Function, FunctionType

from sql_agent.capabilities.embedding.base import Embedder
from sql_agent.capabilities.knoledge_store.schema_documents import DOCUMENT_FORMAT, TEXT_LIMITS

ANALYZER = {"tokenizer": "jieba", "filter": ["lowercase"]}


def collection_profile(embedder: Embedder) -> dict[str, Any]:
    return {"format": DOCUMENT_FORMAT, "embedding": embedder.profile_id,
            "dimensions": embedder.dense_dim, "analyzer": ANALYZER, "bm25": True}


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def ensure_schema_collection(client: Any, *, name: str, embedder: Embedder, timeout: float) -> None:
    profile = collection_profile(embedder)
    if not client.has_collection(collection_name=name, timeout=timeout):
        schema = client.create_schema(
            auto_id=False, enable_dynamic_field=False,
            description=json.dumps(profile, sort_keys=True),
        )
        for field, limit in TEXT_LIMITS.items():
            options: dict[str, Any] = {"max_length": limit}
            if field == "record_id":
                options["is_primary"] = True
            if field == "document_text":
                options.update(enable_analyzer=True, analyzer_params=ANALYZER)
            schema.add_field(field, DataType.VARCHAR, **options)
        schema.add_field("column_count", DataType.INT32)
        schema.add_field("active", DataType.BOOL)
        schema.add_field("updated_at", DataType.INT64)
        schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=embedder.dense_dim)
        schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_function(Function(
            name="schema_bm25", function_type=FunctionType.BM25,
            input_field_names=["document_text"], output_field_names=["sparse_vector"],
        ))
        indexes = client.prepare_index_params()
        indexes.add_index(field_name="dense_vector", index_name="dense_idx", index_type="FLAT", metric_type="COSINE")
        indexes.add_index(field_name="sparse_vector", index_name="sparse_idx", index_type="SPARSE_INVERTED_INDEX", metric_type="BM25")
        client.create_collection(collection_name=name, schema=schema, index_params=indexes,
                                 consistency_level="Strong", timeout=timeout)
    # Also inspect newly created collections: do not silently rely on SDK defaults.
    actual = client.describe_collection(collection_name=name, timeout=timeout)
    try:
        if _json(actual.get("description") or "{}") != profile:
            raise ValueError("模型、维度、文档格式或分词配置不匹配")
        fields = {field["name"]: field for field in actual["fields"]}
        for field, length in TEXT_LIMITS.items():
            info = fields[field]
            if info["type"] != DataType.VARCHAR or int(info["params"]["max_length"]) != length:
                raise ValueError(f"字段定义不匹配：{field}")
        expected = {"dense_vector": DataType.FLOAT_VECTOR, "sparse_vector": DataType.SPARSE_FLOAT_VECTOR,
                    "active": DataType.BOOL, "updated_at": DataType.INT64, "column_count": DataType.INT32}
        if any(fields[field]["type"] != kind for field, kind in expected.items()):
            raise ValueError("向量或标量类型不匹配")
        if int(fields["dense_vector"]["params"]["dim"]) != embedder.dense_dim:
            raise ValueError("向量维度不匹配")
        if actual.get("auto_id") or not fields["record_id"].get("is_primary"):
            raise ValueError("主键配置不匹配")
        params = fields["document_text"]["params"]
        if str(params.get("enable_analyzer")).lower() != "true" or _json(params.get("analyzer_params")) != ANALYZER:
            raise ValueError("BM25 输入分词配置不匹配")
        functions = actual.get("functions", [])
        if not any(fn["type"] == FunctionType.BM25
                   and list(fn["input_field_names"]) == ["document_text"]
                   and list(fn["output_field_names"]) == ["sparse_vector"] for fn in functions):
            raise ValueError("缺少表文档 BM25 Function")
        for index_name, field, index_type, metric in (
            ("dense_idx", "dense_vector", "FLAT", "COSINE"),
            ("sparse_idx", "sparse_vector", "SPARSE_INVERTED_INDEX", "BM25"),
        ):
            index = client.describe_index(collection_name=name, index_name=index_name, timeout=timeout)
            if (index.get("field_name"), index.get("index_type"), index.get("metric_type")) != (field, index_type, metric):
                raise ValueError(f"索引不匹配：{index_name}")
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError(f"Collection {name} 不兼容，请选择新的 MILVUS_SCHEMA_COLLECTION；不会删除旧库") from error
    client.load_collection(collection_name=name, timeout=timeout)
