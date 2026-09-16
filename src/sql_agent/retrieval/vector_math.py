import math


def _require_same_dim(left:list[float],right:list[float]) -> None:
    if len(left) != len(right):
        raise ValueError(
            f"向量维度不一致: left = {len(left)}, right = {len(right)}"
        )

def l2_normalize(vector: list[float]) -> list[float]:
    """把向量变成单位长度（模长为 1）。零向量无法归一化。"""
    if not vector:
        raise ValueError("空向量无法归一化")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        raise ValueError("零向量无法归一化")
    return [value / norm for value in vector]

def cosine_similarity(left: list[float], right: list[float]) -> float:
    """余弦相似度：先各自归一化，再做点积。越大越相似（最大约 1）。"""
    _require_same_dim(left, right)
    left_n = l2_normalize(left)
    right_n = l2_normalize(right)
    return sum(a * b for a, b in zip(left_n, right_n, strict=True))


def inner_product(left: list[float], right: list[float]) -> float:
    """内积（点积）。向量已归一化时，数值上接近余弦相似度。"""
    _require_same_dim(left, right)
    return sum(a * b for a, b in zip(left, right, strict=True))


def l2_distance(left: list[float], right: list[float]) -> float:
    """欧氏距离。越小越近（0 表示完全相同）。"""
    _require_same_dim(left, right)
    return math.sqrt(
        sum((a - b) * (a - b) for a, b in zip(left, right, strict=True))
    )

def brute_force_search(
        query: list[float],
        items: list[tuple[str,list[float]]],
        *,
        top_k: int = 3,
):
    if top_k < 0:
        raise ValueError("top_k 的值必须是大于0的")
    score = [
        (item_id,cosine_similarity(query, vector))
        for item_id,vector in items
    ]
    score.sort(key=lambda x: x[1], reverse=True)
    return score[:top_k]

def main() -> None:
    items = [
        ("recruit", [0.90, 0.10]),
        ("fair", [0.85, 0.18]),
        ("backup", [0.08, 0.95]),
    ]
    query = [0.88, 0.14]

    print("=== 余弦相似度排序（越大越好）===")
    for item_id, score in brute_force_search(query, items, top_k=3):
        print(f"{item_id:8s}  cosine={score:.4f}")

    left, right = [2.0, 1.0], [4.0, 3.0]
    cos = cosine_similarity(left, right)
    ip = inner_product(l2_normalize(left), l2_normalize(right))
    print("归一化后 cosine ≈ ip:", abs(cos - ip) < 1e-6, cos, ip)
    print("L2 recruit:", f"{l2_distance(query, items[0][1]):.4f}")
    print("L2 backup :", f"{l2_distance(query, items[2][1]):.4f}")


if __name__ == "__main__":
    main()
