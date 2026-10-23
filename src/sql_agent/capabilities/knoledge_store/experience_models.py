"""Values shared by confirmed SQL memory and logical relation discovery."""

from dataclasses import dataclass, field
import hashlib
import json


def stable_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class KnowledgeScope:
    tenant_id: str
    database_id: str
    owner_user_id: str

    def __post_init__(self):
        if not all(value.strip() for value in self.values):
            raise ValueError("知识查询缺少服务端数据源或用户范围")

    @property
    def values(self) -> tuple[str, str, str]:
        return self.tenant_id, self.database_id, self.owner_user_id


@dataclass(frozen=True)
class RelationRule:
    left_table: str
    right_table: str
    key_pairs: tuple[tuple[str, str], ...]
    source_fragment: str
    conditions: tuple[str, ...] = ()
    join_type: str = "INNER"
    relation_kind: str = "join"
    aliases: tuple[tuple[str, str], ...] = ()
    join_direction: tuple[str, str] | None = None

    def identity(self, scope: KnowledgeScope) -> str:
        return "rel:" + stable_hash([scope.values, self.left_table, self.right_table, self.key_pairs])


@dataclass
class SqlAnalysis:
    tables: list[str] = field(default_factory=list)
    relations: list[RelationRule] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    schema_complete: bool = True
