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


def _row_count(client: Any, name: str, timeout: float) -> int:
    try:
        stats = client.get_collection_stats(collection_name=name, timeout=timeout)
        if isinstance(stats, dict):
            for key in ("row_count", "rowCount"):
                if stats.get(key) is not None:
                    return int(stats[key])
    except Exception:
        pass
    try:
        index = client.describe_index(collection_name=name, index_name="dense_idx", timeout=timeout) or {}
        return int(index.get("total_rows") or 0)
    except Exception:
        return 0


def collection_incompatibility(
    actual: dict[str, Any],
    embedder: Embedder,
    *,
    indexes: dict[str, dict[str, Any] | None],
    row_count: int = 0,
) -> str | None:
    """Return a reason the collection cannot store current schema docs, or None."""
    desc = _json(actual.get("description") or "{}")
    if not isinstance(desc, dict):
        desc = {}
    if desc.get("format") != DOCUMENT_FORMAT or not desc.get('embedding'):
        return "缺少可核验的文档或模型配置，不会删除原集合，请使用新 Collection 重建"
    stored_dim = desc.get("dimensions")
    if stored_dim not in (None, "", embedder.dense_dim):
        try:
            if int(stored_dim) != embedder.dense_dim:
                return f"向量维度不匹配（collection={stored_dim}，当前={embedder.dense_dim}）"
        except (TypeError, ValueError):
            return "向量维度不匹配"
    stored_embedding = desc.get("embedding")
    dense_info = next((field for field in actual.get('fields', []) if field['name'] == 'dense_vector'), {})
    if int((dense_info.get('params') or {}).get('dim') or 0) != embedder.dense_dim:
        return '向量维度不匹配'
    if (
        stored_embedding
        and stored_embedding != embedder.profile_id
    ):
        return (
            f"集合模型 {stored_embedding} 与当前 {embedder.profile_id} 不同，"
            "不会删除或覆盖原集合，请使用新 Collection 重建"
        )
    if desc.get("analyzer") not in (None, ANALYZER):
        return "分词配置不匹配"
    fields = {field["name"]: field for field in actual.get("fields") or []}
    for field, length in TEXT_LIMITS.items():
        info = fields.get(field)
        if info is None:
            return f"缺少字段：{field}"
        params = info.get("params") or {}
        if info.get("type") != DataType.VARCHAR or int(params.get("max_length") or 0) != length:
            return f"字段定义不匹配：{field}"
    expected = {
        "dense_vector": DataType.FLOAT_VECTOR,
        "sparse_vector": DataType.SPARSE_FLOAT_VECTOR,
        "active": DataType.BOOL,
        "updated_at": DataType.INT64,
        "column_count": DataType.INT32,
    }
    for field, kind in expected.items():
        info = fields.get(field)
        if info is None or info.get("type") != kind:
            return f"字段类型不匹配：{field}"
    dense_params = fields["dense_vector"].get("params") or {}
    if int(dense_params.get("dim") or 0) != embedder.dense_dim:
        return f"向量维度不匹配（collection={dense_params.get('dim')}，当前={embedder.dense_dim}）"
    if actual.get("auto_id") or not fields["record_id"].get("is_primary"):
        return "主键配置不匹配"
    params = fields["document_text"].get("params") or {}
    if str(params.get("enable_analyzer")).lower() != "true" or _json(params.get("analyzer_params")) != ANALYZER:
        return "BM25 输入分词配置不匹配"
    functions = actual.get("functions") or []
    if not any(
        fn.get("type") == FunctionType.BM25
        and list(fn.get("input_field_names") or []) == ["document_text"]
        and list(fn.get("output_field_names") or []) == ["sparse_vector"]
        for fn in functions
    ):
        return "缺少表文档 BM25 Function"
    for index_name, field, index_type, metric in (
        ("dense_idx", "dense_vector", "FLAT", "COSINE"),
        ("sparse_idx", "sparse_vector", "SPARSE_INVERTED_INDEX", "BM25"),
    ):
        index = indexes.get(index_name) or {}
        if (index.get("field_name"), index.get("index_type"), index.get("metric_type")) != (
            field,
            index_type,
            metric,
        ):
            return f"索引不匹配：{index_name}"
    return None


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
    actual = client.describe_collection(collection_name=name, timeout=timeout)
    index_info: dict[str, dict[str, Any] | None] = {}
    for index_name in ("dense_idx", "sparse_idx"):
        try:
            index_info[index_name] = client.describe_index(
                collection_name=name, index_name=index_name, timeout=timeout
            )
        except Exception:
            index_info[index_name] = None
    reason = collection_incompatibility(
        actual,
        embedder,
        indexes=index_info,
        row_count=_row_count(client, name, timeout),
    )
    if reason:
        raise ValueError(f"Collection {name} 不能用于当前同步：{reason}")
    client.load_collection(collection_name=name, timeout=timeout)
