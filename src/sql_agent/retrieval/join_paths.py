"""Bounded, iterative BFS over confirmed, source-scoped logical JOIN rules."""

from collections import deque


def find_join_path(store, scope, catalog, source: str, target: str, *,
                   max_hops: int = 3, max_nodes: int = 50, max_edges: int = 100,
                   relation_ids: list[str] | None = None) -> dict:
    if not (1 <= max_hops <= 6 and 2 <= max_nodes <= 100 and 1 <= max_edges <= 200):
        raise ValueError("关系搜索预算超出允许范围")
    source, target = catalog.resolve(source), catalog.resolve(target)
    queue = deque([(source, 0)])
    previous = {source: None}
    checked = set()
    depth_limited = False
    evidence_limited = False
    ambiguities = []
    allowed = set(relation_ids or [])

    def response(status, **extra):
        return {"status": status, "path": [], "visited_nodes": len(previous), "checked_edges": len(checked), **extra}

    if source == target:
        return response("found", path=[source], relations=[], tables=catalog.documents([source]))
    while queue:
        current, depth = queue.popleft()
        remaining = max_edges - len(checked)
        if remaining <= 0:
            return response("budget_exhausted")
        rows = store.neighbors(scope, current, remaining + 1)
        groups = {}
        for edge in rows[:remaining]:
            checked.add(edge["relation_id"])
            neighbor = edge["right_table"] if edge["left_table"] == current else edge["left_table"]
            groups.setdefault(neighbor, []).append(edge)
        for neighbor, edges in groups.items():
            if neighbor in previous:
                continue
            # Choices disambiguate this table pair, not every edge in the path.
            # Select before schema validation: never silently replace a stale
            # selected role with a different role between the same tables.
            selected = [edge for edge in edges if edge["relation_id"] in allowed]
            valid = []
            for edge in selected or edges:
                sources = [ev for ev in edge["sources"] if catalog.compatible(ev["schema_fingerprints"])]
                if sources:
                    valid.append({**edge, "sources": sources[:3]})
                elif edge.get("sources_truncated"):
                    evidence_limited = True
            edges = valid
            if not edges:
                continue
            if depth >= max_hops:
                depth_limited = True
                continue
            if len(edges) > 1:
                ambiguities.extend(edges[:max(0, 3 - len(ambiguities))])
                continue
            edge = edges[0]
            if len(previous) >= max_nodes:
                return response("budget_exhausted")
            previous[neighbor] = (current, edge)
            if neighbor == target:
                path, relations, node = [target], [], target
                while previous[node] is not None:
                    node, relation = previous[node]
                    path.append(node)
                    relations.append(relation)
                path.reverse()
                relations.reverse()
                return response("found", path=path, relations=relations, tables=catalog.documents(path),
                                note="连接来自用户确认的 SQL；来源中的筛选条件仍需按本题判断，不能当作数据库外键")
            queue.append((neighbor, depth + 1))
        if len(rows) > remaining:
            return response("budget_exhausted")
    if ambiguities:
        return response("ambiguous", candidates=ambiguities,
                        message="同一表对存在不同连接规则，请参考来源 SQL 并用 relation_ids 限定规则")
    status = "budget_exhausted" if depth_limited or evidence_limited else "empty_graph" if not checked else "no_path"
    return response(status, message="当前已知关系及搜索范围内未找到连接路径")
