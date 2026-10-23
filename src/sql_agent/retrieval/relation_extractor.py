"""Resolve logical keys without inferring foreign keys or discarding applicability."""

from collections import defaultdict
from dataclasses import dataclass

from sqlglot import exp, parse_one
from sqlglot.optimizer.scope import Scope, traverse_scope

from sql_agent.capabilities.knoledge_store.experience_models import RelationRule, SqlAnalysis
from sql_agent.integrations.db.sql_validate import sql_dialect


def _conjuncts(node):
    if isinstance(node, exp.Paren):
        return _conjuncts(node.this)
    if isinstance(node, exp.And):
        return _conjuncts(node.this) + _conjuncts(node.expression)
    return [node]


@dataclass(frozen=True)
class _Origin:
    table: str
    column: str
    instance: tuple
    conditions: tuple[str, ...] = ()


class _Resolver:
    def __init__(self, catalog):
        self.catalog = catalog

    def column(self, column, scope, seen=frozenset()):
        marker = (id(scope), column.table.casefold(), column.name.casefold())
        if marker in seen or len(seen) > 20:
            raise ValueError("递归/过深的字段来源不发布关系")
        seen = seen | {marker}
        sources = {alias.casefold(): source for alias, (_, source) in scope.selected_sources.items()}
        if column.table:
            alias = column.table.casefold()
            if alias in sources:
                return self.source(sources[alias], alias, column.name, scope, seen)
            if scope.can_be_correlated and scope.parent is not None:
                return self.column(column, scope.parent, seen)
            raise ValueError("连接别名无法在当前或合法外层作用域解析")
        candidates = []
        for alias, source in sources.items():
            try:
                candidates.append(self.source(source, alias, column.name, scope, seen))
            except ValueError:
                pass
        if len(candidates) == 1:
            return candidates[0]
        if not candidates and scope.can_be_correlated and scope.parent is not None:
            if any(isinstance(source, Scope) and any(
                    output.casefold() == column.name.casefold() for output in
                    (source.outer_columns or [item.alias_or_name for item in source.expression.selects]))
                   for source in sources.values()):
                raise ValueError("本地派生字段遮蔽外层字段，不能跨作用域误配")
            return self.column(column, scope.parent, seen)
        raise ValueError("未限定字段无法唯一归属")

    def source(self, source, alias, name, scope, seen):
        if isinstance(source, exp.Table):
            if source.catalog:
                raise ValueError("不推断跨 catalog 连接")
            table = self.catalog.resolve(source.name, source.db or None)
            return _Origin(table, self.catalog.column(table, name), (id(scope), alias))
        if not isinstance(source, Scope) or not isinstance(source.expression, exp.Select):
            raise ValueError("UNION/递归或未知派生来源不发布关系")
        outputs = source.expression.selects
        names = source.outer_columns or [item.alias_or_name for item in outputs]
        matches = [item for output, item in zip(names, outputs) if output.casefold() == name.casefold()]
        if not matches and len(outputs) == 1 and isinstance(outputs[0], exp.Star) and len(source.selected_sources) == 1:
            matches = [exp.column(name)]
        if len(matches) != 1:
            raise ValueError("派生字段来源不存在或不唯一")
        expression = matches[0].this if isinstance(matches[0], exp.Alias) else matches[0]
        if not isinstance(expression, exp.Column) or expression.is_star:
            raise ValueError("计算/聚合派生字段不能当作连接键")
        origin = self.column(expression, source, seen)
        conditions = origin.conditions + ("派生来源：" + source.expression.sql(),)
        return _Origin(origin.table, origin.column, (id(scope), alias, origin.instance), conditions)


def _simple_filter(predicate, resolver, scope):
    """Allow scalar filters; never flatten OR, functions or subqueries."""
    allowed = (exp.Column, exp.Identifier, exp.Literal, exp.Null, exp.Boolean,
               exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Is,
               exp.In, exp.Between, exp.Not, exp.Paren, exp.Neg)
    if not all(isinstance(node, allowed) for node in predicate.walk()):
        return False
    columns = list(predicate.find_all(exp.Column))
    if not columns:
        return False
    origins = [resolver.column(column, scope) for column in columns]
    return len({origin.table for origin in origins}) == 1


def analyze_sql(sql: str, dialect: str, catalog) -> SqlAnalysis:
    result = SqlAnalysis()
    query = parse_one(sql, read=sql_dialect(dialect))
    resolver, unique = _Resolver(catalog), {}
    for scope in traverse_scope(query):
        for _, (_, source) in scope.selected_sources.items():
            if isinstance(source, exp.Table):
                try:
                    if source.catalog:
                        raise ValueError("不推断跨 catalog 连接")
                    result.tables.append(catalog.resolve(source.name, source.db or None))
                except ValueError as error:
                    result.schema_complete = False
                    result.skipped.append(str(error))

        def publish(condition, *, kind, join_type="INNER", joined_alias=None, strict=False):
            try:
                groups, filters, origins = defaultdict(list), [], []
                for predicate in _conjuncts(condition):
                    if (isinstance(predicate, exp.EQ) and isinstance(predicate.this, exp.Column)
                            and isinstance(predicate.expression, exp.Column)):
                        left = resolver.column(predicate.this, scope)
                        right = resolver.column(predicate.expression, scope)
                        if left.table == right.table:
                            if left.instance != right.instance:
                                raise ValueError("自连接需要显式业务角色，整组不发布")
                            filters.append(predicate.sql())
                            continue
                        origins.extend((left, right))
                        if left.table > right.table:
                            left, right = right, left
                        groups[(left.table, right.table)].append((left.column, right.column))
                    elif strict and not _simple_filter(predicate, resolver, scope):
                        raise ValueError("ON 含 OR、非等值跨表、函数或子查询条件，整组不发布")
                    else:
                        filters.append(predicate.sql())
                if strict and len(groups) > 1:
                    raise ValueError("同一 ON 依赖多个表对，暂不拆成独立连接")
                if strict and groups:
                    pair = next(iter(groups))
                    if any(resolver.column(column, scope).table not in pair for column in condition.find_all(exp.Column)):
                        raise ValueError("ON 条件还依赖第三张表，暂不拆成独立连接")
                where = scope.expression.args.get("where")
                conditions = filters + [c for origin in origins for c in origin.conditions]
                if where is not None:
                    conditions.append("来源 WHERE：" + where.this.sql())
                aliases = []
                for column in condition.find_all(exp.Column):
                    if column.table:
                        try:
                            aliases.append((column.table, resolver.column(column, scope).table))
                        except ValueError:
                            pass
                for (left, right), pairs in groups.items():
                    pairs = tuple(sorted(set(pairs)))
                    joined_table = next((table for alias, table in aliases if alias.casefold() == (joined_alias or "").casefold()), None)
                    direction = ((right if joined_table == left else left), joined_table) if joined_table in (left, right) else None
                    rule = RelationRule(left, right, pairs, condition.sql(),
                                        tuple(dict.fromkeys(conditions)), join_type, kind,
                                        tuple(sorted(set(aliases))), direction)
                    key = (left, right, pairs)
                    if key in unique:
                        old = unique[key]
                        rule = RelationRule(left, right, pairs,
                                            old.source_fragment + "\n另一个来源位置：" + rule.source_fragment,
                                            tuple(dict.fromkeys(old.conditions + rule.conditions)),
                                            "MULTIPLE", "multiple", tuple(sorted(set(old.aliases + rule.aliases))))
                    unique[key] = rule
            except ValueError as error:
                result.skipped.append(str(error))

        for join in scope.expression.args.get("joins") or []:
            on = join.args.get("on")
            if on is None:
                if join.args.get("using"):
                    result.skipped.append("USING 暂不推断字段归属")
                continue
            join_type = " ".join(filter(None, [join.args.get("side"), join.args.get("kind")])) or "INNER"
            publish(on, kind="join", join_type=join_type, joined_alias=join.this.alias_or_name, strict=True)
        where = scope.expression.args.get("where")
        if where is not None:
            kind = "where"
            parent = scope.expression.parent
            if isinstance(parent, exp.Exists):
                kind = "not_exists" if isinstance(parent.parent, exp.Not) else "exists"
            publish(where.this, kind=kind)
    result.tables = sorted(set(result.tables))
    result.relations = list(unique.values())
    return result
