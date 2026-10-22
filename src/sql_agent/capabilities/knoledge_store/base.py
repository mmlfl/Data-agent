from abc import ABC, abstractmethod

from sql_agent.capabilities.knoledge_store.models import KnowledgeSearchQuery, KnowledgeRecord, KnowledgeHit, \
    KnowledgeScope


class KnowledgeStore(ABC):
    """知识库抽象：upsert / search / delete；不负责拼 prompt 或调 LLM。"""

    @abstractmethod
    def upsert(self, records: list[KnowledgeRecord]) -> int:
        """写入或覆盖记录，返回成功条数。"""

    @abstractmethod
    def search(self, query: KnowledgeSearchQuery) -> list[KnowledgeHit]:
        """按 scope 过滤后做近邻检索；只返回可在线展示的命中。"""

    @abstractmethod
    def delete_ids(self, scope: KnowledgeScope, record_ids: list[str]) -> int:
        """仅删除属于该 scope 的 id；越权 id 应跳过。必须带 scope。"""

    @abstractmethod
    def close(self) -> None:
        """释放底层客户端等资源。"""