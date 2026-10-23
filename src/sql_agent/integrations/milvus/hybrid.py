"""Dense + server-side BM25 with identical filters on both recall branches."""

from pymilvus import AnnSearchRequest, RRFRanker


def hybrid_search(client, *, collection: str, embedder, question: str, expression: str,
                  parameters: dict, output_fields: list[str], limit: int, timeout: float) -> list[dict]:
    vector = embedder.encode_query(question).dense
    requests = [
        AnnSearchRequest(data=[vector], anns_field="dense_vector", param={"metric_type": "COSINE"},
                         limit=10, expr=expression, expr_params=parameters),
        AnnSearchRequest(data=[question], anns_field="sparse_vector", param={"metric_type": "BM25"},
                         limit=10, expr=expression, expr_params=parameters),
    ]
    results = client.hybrid_search(collection_name=collection, reqs=requests, ranker=RRFRanker(k=60),
                                   limit=limit, output_fields=output_fields, timeout=timeout,
                                   consistency_level="Strong")
    return [{**hit.get("entity", {}), "score": hit.get("distance")} for hit in (results[0] if results else [])]
