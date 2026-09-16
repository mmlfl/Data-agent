from __future__ import annotations

import random
import time
import uuid

from pymilvus import DataType, MilvusClient

from sql_agent.integrations.milvus.base import client
from sql_agent.integrations.milvus.client import create_milvus_client
from sql_agent.integrations.milvus.schema import (
    drop_test_collection,
    ensure_dense_collection, assert_test_collection_name,
)
from sql_agent.integrations.milvus.settings import MilvusSettings


def pad8(values: list[float]) -> list[float]:
    return values + [0.0] * (8 - len(values))


def main() -> None:
    settings = MilvusSettings()
    name = f"sql_agent_test_lifecycle_{uuid.uuid4().hex[:8]}"
    client = create_milvus_client(settings)
    timeout = settings.milvus_connect_timeout_seconds
    try:
        ensure_dense_collection(client, collection_name=name)
        print("has_collection:", client.has_collection(name))
        print("describe_collection:", client.describe_collection(name))
        print("list_indexes:", client.list_indexes(name))
    finally:
        drop_test_collection(client, name)
        client.close()


DIM = 100
N = 200

def make_vectors(n: int) -> list[list[float]]:
    rng = random.Random(42)
    vectors: list[list[float]] = []
    for _ in range(n):
        raw = [rng.random() for _ in range(DIM)]
        norm = sum(v * v for v in raw) ** 0.5 or 1.0
        vectors.append([v / norm for v in raw])
    return vectors

def create_with_index(client:MilvusClient,name:str,*,index_type:str,index_params:dict)->None:
    assert_test_collection_name(name)
    if client.has_collection(name):
        client.drop_collection(name)

    schema = client.create_schema(
        auto_id=False,
        enable_dynamic_field=False,
    )

    schema.add_field("id",DataType.VARCHAR,is_primary=True,max_length=64)
    schema.add_field("dense_vector",DataType.FLOAT_VECTOR,dim=DIM)

    ip = client.prepare_index_params()
    ip.add_index(
        field_name="dense_vector",
        index_type=index_type,
        metric_type="COSINE",
        params=index_params,
    )

    client.create_collection(
        collection_name=name,
        schema=schema,
        index_params=ip,
        consistency_level="Strong",
    )

# name1 = f"sql_agent_test_idx_flat_{uuid.uuid4().hex[:8]}"
# create_with_index(client, name1, index_type="FLAT", index_params={})
#
# name2 = f"sql_agent_test_idx_ivf_flat_{uuid.uuid4().hex[:8]}"
# create_with_index(client, name2, index_type="IVF_FLAT", index_params={"nlist":64})
#
# name3 = f"sql_agent_test_idx_hnsw_{uuid.uuid4().hex[:8]}"
# create_with_index(client, name3, index_type="HNSW", index_params={"M":16,"efConstruction":200})

def benchmark(client:MilvusClient, name: str, vectors: list[list[float]], search_params: dict) -> dict:
    timeout = MilvusSettings().milvus_connect_timeout_seconds
    rows = [{"id": f"row-{i}", "dense_vector": vec} for i, vec in enumerate(vectors)]

    t0 = time.perf_counter()
    client.insert(collection_name=name, data=rows, timeout=timeout)
    client.flush(name)
    build_s = time.perf_counter() - t0

    query = vectors[0]
    client.search(  # 预热
        collection_name=name, data=[query], anns_field="dense_vector",
        limit=10, search_params=search_params, timeout=timeout,
    )

    latencies: list[float] = []
    for _ in range(30):
        s = time.perf_counter()
        client.search(
            collection_name=name, data=[query], anns_field="dense_vector",
            limit=10, search_params=search_params, timeout=timeout,
        )
        latencies.append((time.perf_counter() - s) * 1000)
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95) - 1]
    return {"build_s": round(build_s, 3), "p50_ms": round(p50, 2), "p95_ms": round(p95, 2)}


def compute_recall(ground_truth_ids: list[str], result_ids: list[str]) -> float:
    """计算召回率：预测结果中有多少比例命中了标准答案"""
    ground_truth_set = set(ground_truth_ids)
    hit = sum(1 for id_ in result_ids if id_ in ground_truth_set)
    return hit / len(ground_truth_set)


def main() -> None:
    settings = MilvusSettings()
    client = create_milvus_client(settings)
    timeout = settings.milvus_connect_timeout_seconds

    N = 300_000
    TOP_K = 15
    BATCH_SIZE = 2000
    SEARCH_TIMES = 20

    print(f"数据量: {N} 条, 维度: {DIM}, Top-K: {TOP_K}")
    print("生成向量中...")
    vectors = make_vectors(N)
    query = vectors[0]
    rows = [{"id": f"row-{i}", "dense_vector": vec} for i, vec in enumerate(vectors)]

    # ========== 通用：建集合 → 插数据 → flush → 建索引 → load ==========
    def build_collection(name: str, index_type: str, index_params: dict) -> None:
        assert_test_collection_name(name)

        # 1. 建集合（不带索引）
        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=DIM)
        client.create_collection(
            collection_name=name, schema=schema, consistency_level="Strong",
        )

        # 2. 插数据
        t0 = time.perf_counter()
        for i in range(0, len(rows), BATCH_SIZE):
            client.insert(collection_name=name, data=rows[i:i + BATCH_SIZE], timeout=timeout)
        client.flush(name)
        print(f"[{index_type}] 插入耗时: {time.perf_counter() - t0:.2f}s")

        # 3. 数据封存后，再建索引
        ip = client.prepare_index_params()
        ip.add_index(
            field_name="dense_vector",
            index_type=index_type,
            metric_type="COSINE",
            params=index_params,
        )
        client.create_index(collection_name=name, index_params=ip)
        client.load_collection(name)

        # 4. 检查索引
        idx_info = client.describe_index(collection_name=name, index_name="dense_vector")
        print(f"[{index_type}] 索引详情: {idx_info}")

    # ========== 1. 用 FLAT 建标准答案 ==========
    print("\n" + "=" * 60)
    print("建立 FLAT 标准答案...")
    print("=" * 60)
    flat_name = f"sql_agent_test_flat_{uuid.uuid4().hex[:8]}"
    build_collection(flat_name, "FLAT", {})

    flat_hits = client.search(
        collection_name=flat_name, data=[query], anns_field="dense_vector",
        limit=TOP_K, search_params={"metric_type": "COSINE"}, timeout=timeout,
    )
    ground_truth_ids = [hit["id"] for hit in flat_hits[0]]
    print(f"标准答案: {ground_truth_ids}")
    print(f"标准答案去重后数量: {len(set(ground_truth_ids))}")

    # FLAT 自己搜自己，验证标准答案稳定性
    flat_hits2 = client.search(
        collection_name=flat_name, data=[query], anns_field="dense_vector",
        limit=TOP_K, search_params={"metric_type": "COSINE"}, timeout=timeout,
    )
    ids2 = [hit["id"] for hit in flat_hits2[0]]
    print(f"FLAT 自己搜自己召回率: {compute_recall(ground_truth_ids, ids2)}")

    client.drop_collection(flat_name)

    # ========== 3. 测试 HNSW ==========
    print("\n" + "=" * 60)
    print("测试 HNSW (M=16, efConstruction=200)")
    print("=" * 60)
    hnsw_name = f"sql_agent_test_hnsw_{uuid.uuid4().hex[:8]}"
    build_collection(hnsw_name, "HNSW", {"M": 64, "efConstruction": 200})

    print(f"\n{'ef':<10} {'P50(ms)':<10} {'P95(ms)':<10} {'平均(ms)':<10} {'召回率(%)':<10} {'首条ID':<15}")
    print("-" * 75)
    for ef in [16, 32, 64, 128, 256, 512]:
        params = {"metric_type": "COSINE", "params": {"ef": ef}}
        client.search(
            collection_name=hnsw_name, data=[query], anns_field="dense_vector",
            limit=TOP_K, search_params=params, timeout=timeout,
        )
        latencies, recalls, first_ids = [], [], []
        for _ in range(SEARCH_TIMES):
            s = time.perf_counter()
            hits = client.search(
                collection_name=hnsw_name, data=[query], anns_field="dense_vector",
                limit=TOP_K, search_params=params, timeout=timeout,
            )
            latencies.append((time.perf_counter() - s) * 1000)
            result_ids = [hit["id"] for hit in hits[0]]
            first_ids.append(result_ids[0])
            recalls.append(compute_recall(ground_truth_ids, result_ids))

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95) - 1]
        avg_lat = sum(latencies) / len(latencies)
        avg_recall = sum(recalls) / len(recalls)
        first_id = first_ids[0] if first_ids else "N/A"
        print(f"{ef:<10} {round(p50, 2):<10} {round(p95, 2):<10} {round(avg_lat, 2):<10} {round(avg_recall * 100, 2):<10} {first_id:<15}")

    client.drop_collection(hnsw_name)
    client.close()


if __name__ == "__main__":
    main()