from sql_agent.integrations.milvus.base import client, COLLECTION_NAME
from sql_agent.integrations.milvus.schema import pad8
from sql_agent.retrieval.vector_math import brute_force_search


def test_semantically_close_fake_vectors_rank_first() -> None:
    items = [
        ("recruit", [0.90, 0.10]),
        ("backup", [0.08, 0.95]),
    ]
    query = [0.88, 0.14]
    result = brute_force_search(query, items, top_k=1)
    assert result[0][0] == "recruit"

def test_semantically_close_fake_vectors_rank_last() -> None:
    query = pad8([0.88,0.14])
    timeout = 30
    hits = client.search(
        collection_name=COLLECTION_NAME,
        data=[query],
        anns_field="dense_vector",
        limit=3,
        output_fields=["text","database_id","tenant_id","active"],
        search_params={"metric_type":"COSINE"},
        timeout=timeout,
    )

    print("====MILVUS SEARCH====")
    for hits_per_query in hits:
        for hit in hits_per_query:
            print(hit["id"],round(hit["distance"],4),hit["entity"]["text"])
