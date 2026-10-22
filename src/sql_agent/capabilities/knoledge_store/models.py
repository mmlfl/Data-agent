from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class KnowledgeKind(StrEnum):
    """milvus 存储类型"""
    QUESTION_SQL = "question_sql"
    DDL = "ddl"
    DOCUMENTATION = "documentation"

class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class KnowledgeRecord(BaseModel):
    record_id: str = Field(description="稳定主键，含租户等作用域")
    kind : KnowledgeKind
    dense_text: str = Field(description="用于dense embedding 的文本")
    lexical_text: str = Field(description="用于关键词/稀疏检索的文本")
    content: str = Field(description="返回给LLM的正文")
    source: str = Field(
        description="来源标记，如 manual / jsonl / schema_cache / agent"
    )
    approval_status: ApprovalStatus = Field(
        default = ApprovalStatus.PENDING,
        description= "在线 search 只应过滤 approved"
    )
    active: bool = Field(default = True,description="False 表示软下线")
    content_hash: str = ""
    version: int = 1
    acl_groups: list[str] = Field(default_factory=list)
    metadata : dict[str,Any] = Field(default_factory=dict)


class KnowledgeScope(BaseModel):
    """带权限的检索 后期维护"""
    acl_groups: list[str] = Field(default_factory=list)

class KnowledgeSearchQuery(BaseModel):
    """ 一次检索请求 """
    text: str = Field(description="检索用自然语言")
    scope:KnowledgeScope = Field(description="数据库,租户啥的权限要求")
    top_k: int = 5
    kinds: list[KnowledgeKind] | None = Field(
        default=None,
        description="搜索对应的知识类型,如果是None就代表全部类型都会去搜索",
    )

class KnowledgeHit(BaseModel):
    """ 单条检索命中 """
    record_id: str
    score: float
    kind: KnowledgeKind
    content: str
    dense_text: str = ""
    lexical_text: str = ""
    metadata: dict[str,Any] = Field(default_factory=dict)