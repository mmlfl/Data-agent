"""Structural checks for aggregation plans; business correctness is not inferred."""

from sqlglot import exp, parse_one
from sqlglot.optimizer.scope import Scope, traverse_scope

from sql_agent.integrations.db.sql_validate import sql_dialect


def review_query(sql, dialect, plan):
    tree = parse_one(sql, read=sql_dialect(dialect))
    joined_aggregates, raw_measures = [], []
    grouped_sources = []
    for scope in traverse_scope(tree):
        if not isinstance(scope.expression, exp.Select):
            continue
        # Stop at nested query boundaries: their aggregates have their own grain.
        aggregates = []
        for node in scope.expression.walk(prune=lambda n: n is not scope.expression and isinstance(n, exp.Query)):
            if isinstance(node, exp.AggFunc):
                aggregates.append(node)
        if len(scope.selected_sources) > 1 and aggregates:
            joined_aggregates.extend(aggregates)
            for node in aggregates:
                if isinstance(node, (exp.Sum, exp.Avg)):
                    raw_measures.append(node)
            grouped_sources.append(any(
                isinstance(source, Scope) and source.expression.args.get("group") is not None
                for _, source in scope.selected_sources.values()))
    if not joined_aggregates:
        return None
    if plan is None:
        return {"error_code": "sql_plan_required", "repairable": True,
                "hint": "多表聚合执行前请补 query_plan：grain、metrics、filters、join_purpose、fanout_strategy、evidence；明确一对多是否重复计数，不要直接重跑同一请求。"}
    strategy = plan.fanout_strategy
    if strategy == "not_applicable":
        return {"error_code": "sql_grain_unverified", "repairable": True,
                "hint": "多表聚合需要明确防重复策略；只用于筛选的子表可用 EXISTS，或先聚合再关联。关系/口径不明确请澄清。"}
    if strategy == "exists":
        return {"error_code": "sql_plan_mismatch", "repairable": True,
                "hint": "聚合所在层仍关联多个来源，EXISTS 不能证明这些 JOIN 不放大指标；请将仅筛选的关联改为 EXISTS，或明确其他连接基数/预聚合策略。"}
    if strategy == "preaggregate" and not all(grouped_sources):
        return {"error_code": "sql_plan_mismatch", "repairable": True, "hint": "计划声明先聚合，但聚合关联处没有 GROUP BY 派生来源/CTE，请先按连接粒度聚合。"}
    if strategy == "count_distinct" and (raw_measures or not all(
            isinstance(node, exp.Count) and isinstance(node.this, exp.Distinct) for node in joined_aggregates)):
        return {"error_code": "sql_plan_mismatch", "repairable": True,
                "hint": "count_distinct 仅适用于全部指标均为 COUNT(DISTINCT ...)，不能保护 SUM/AVG 或其他未去重指标。不要用 SUM(DISTINCT 金额) 替代实体去重。"}
    return None
