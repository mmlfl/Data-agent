"""Independent confirmed-question/SQL collection, incompatible with schema/lab rows."""

import json

from pymilvus import DataType, Function, FunctionType

from sql_agent.integrations.milvus.schema_collection import ANALYZER

MEMORY_TEXT_FIELDS = {
    "memory_id": 128, "source_query_id": 128, "tenant_id": 128,
    "database_id": 128, "owner_user_id": 128, "content_hash": 64,
    "search_text": 65535, "question": 65535, "sql": 65535,
    "tables_json": 65535, "schema_fingerprints_json": 65535,
}


def ensure_memory_collection(client, *, name: str, embedder, timeout: float):
    profile = {"format": "confirmed-sql-v1", "embedding": embedder.profile_id,
               "dimensions": embedder.dense_dim, "analyzer": ANALYZER, "bm25": True}
    if not client.has_collection(collection_name=name, timeout=timeout):
        schema = client.create_schema(auto_id=False, enable_dynamic_field=False,
                                      description=json.dumps(profile, sort_keys=True))
        for field, length in MEMORY_TEXT_FIELDS.items():
            options = {"max_length": length}
            if field == "memory_id":
                options["is_primary"] = True
            if field == "search_text":
                options.update(enable_analyzer=True, analyzer_params=ANALYZER)
            schema.add_field(field, DataType.VARCHAR, **options)
        schema.add_field("active", DataType.BOOL)
        schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=embedder.dense_dim)
        schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_function(Function(name="memory_bm25", function_type=FunctionType.BM25,
                                    input_field_names=["search_text"], output_field_names=["sparse_vector"]))
        indexes = client.prepare_index_params()
        indexes.add_index(field_name="dense_vector", index_name="dense_idx", index_type="FLAT", metric_type="COSINE")
        indexes.add_index(field_name="sparse_vector", index_name="sparse_idx", index_type="SPARSE_INVERTED_INDEX", metric_type="BM25")
        client.create_collection(collection_name=name, schema=schema, index_params=indexes,
                                 consistency_level="Strong", timeout=timeout)
    actual = client.describe_collection(collection_name=name, timeout=timeout)
    try:
        if json.loads(actual.get("description") or "{}") != profile:
            raise ValueError("模型或文本格式不匹配")
        fields = {item["name"]: item for item in actual["fields"]}
        for field, length in MEMORY_TEXT_FIELDS.items():
            if fields[field]["type"] != DataType.VARCHAR or int(fields[field]["params"]["max_length"]) != length:
                raise ValueError("字段不匹配")
        if actual.get("auto_id") or not fields["memory_id"].get("is_primary"):
            raise ValueError("主键不匹配")
        if fields["dense_vector"]["type"] != DataType.FLOAT_VECTOR or int(fields["dense_vector"]["params"]["dim"]) != embedder.dense_dim:
            raise ValueError("向量不匹配")
        if fields["sparse_vector"]["type"] != DataType.SPARSE_FLOAT_VECTOR or fields["active"]["type"] != DataType.BOOL:
            raise ValueError("稀疏或状态字段不匹配")
        params = fields["search_text"]["params"]
        analyzer = params.get("analyzer_params")
        if isinstance(analyzer, str):
            analyzer = json.loads(analyzer)
        if str(params.get("enable_analyzer")).lower() != "true" or analyzer != ANALYZER:
            raise ValueError("分词配置不匹配")
        if not any(fn["type"] == FunctionType.BM25 and list(fn["input_field_names"]) == ["search_text"]
                   and list(fn["output_field_names"]) == ["sparse_vector"] for fn in actual.get("functions", [])):
            raise ValueError("BM25 Function 不匹配")
        for index_name, field, kind, metric in (("dense_idx", "dense_vector", "FLAT", "COSINE"),
                                                ("sparse_idx", "sparse_vector", "SPARSE_INVERTED_INDEX", "BM25")):
            index = client.describe_index(collection_name=name, index_name=index_name, timeout=timeout)
            if (index.get("field_name"), index.get("index_type"), index.get("metric_type")) != (field, kind, metric):
                raise ValueError("索引不匹配")
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("记忆 Collection 不兼容，请使用新的 MILVUS_MEMORY_COLLECTION；旧库不会删除") from error
    client.load_collection(collection_name=name, timeout=timeout)
