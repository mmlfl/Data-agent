from pymilvus import MilvusClient, DataType


DENSE_BASICS_DIM = 8

def assert_test_collection_name(collection_name:str)->None:
    if not collection_name.startswith("sql_agent_test_"):
        raise ValueError(
            f"拒绝操作非测试 Collection : {collection_name!r}"
            f"(必须以 sql_agent_test_ 开头)"
        )

def drop_test_collection(client: MilvusClient,collection_name:str)->None:
    assert_test_collection_name(collection_name)
    if client.has_collection(collection_name):
        client.drop_collection(collection_name)


def ensure_dense_collection(
        client: MilvusClient,
        *,
        collection_name:str,
        dense_dim: int=DENSE_BASICS_DIM,
        consistency_level: str="Strong",
)->None:
    if client.has_collection(collection_name):
        return
    schema = client.create_schema(
        auto_id=False,
        enable_dynamic_field=False,
    )
    schema.add_field(
        field_name="id",
        datatype=DataType.VARCHAR,
        is_primary=True,
        max_length=64,
    )
    schema.add_field(
        field_name="dense_vector",
        datatype=DataType.FLOAT_VECTOR,
        dim=dense_dim,
    )
    schema.add_field(
        field_name="text",
        datatype=DataType.VARCHAR,
        max_length=2048,
    )
    schema.add_field(
        field_name="database_id",
        datatype=DataType.VARCHAR,
        max_length=128,
    )
    schema.add_field("tenant_id", DataType.VARCHAR, max_length=128)
    schema.add_field("active", DataType.BOOL)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="dense_vector",
        index_type="FLAT",
        metric_type="COSINE",
    )

    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
        consistency_level=consistency_level,
    )

def pad8(values: list[float]) -> list[float]:
    if len(values) > DENSE_BASICS_DIM:
        raise ValueError("向量太长")
    return values + [0.0] * (DENSE_BASICS_DIM - len(values))

def mock_data(client:MilvusClient,collection_name:str)->None:
    rows = [
        {
            "id": "recruit",
            "text": "最近有什么招聘会",
            "database_id": "career_demo",
            "tenant_id": "local",
            "active": True,
            "dense_vector": pad8([0.90, 0.10]),
        },
        {
            "id": "fair",
            "text": "近期双选会安排",
            "database_id": "career_demo",
            "tenant_id": "local",
            "active": True,
            "dense_vector": pad8([0.85, 0.18]),
        },
        {
            "id": "backup",
            "text": "达梦数据库备份",
            "database_id": "ops_demo",
            "tenant_id": "local",
            "active": True,
            "dense_vector": pad8([0.08, 0.95]),
        },
    ]
    client.insert(
        collection_name=collection_name,
        data=rows,
        timeout=30,
    )
    print("inserted:", len(rows))
