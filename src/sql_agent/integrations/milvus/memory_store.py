"""Lazy cloud resources: ordinary execution never connects to the vector service."""

import json
import math
import threading

from sql_agent.capabilities.embedding.settings import EmbeddingSettings
from sql_agent.integrations.embedding.aliyun import AliyunEmbedder
from sql_agent.integrations.milvus.client import create_milvus_client
from sql_agent.integrations.milvus.hybrid import hybrid_search
from sql_agent.integrations.milvus.memory_collection import MEMORY_TEXT_FIELDS, ensure_memory_collection
from sql_agent.integrations.milvus.schema_collection import ensure_schema_collection


class KnowledgeVectors:
    def __init__(self, settings):
        if settings.milvus_schema_collection == settings.milvus_memory_collection:
            raise ValueError("单表和 SQL 记忆必须使用不同的 Collection")
        self.settings = settings
        self._client = None
        self._embedder = None
        self._ready = set()
        self._lock = threading.RLock()

    @property
    def enabled(self):
        return self.settings.rag_enabled

    def _resources(self):
        with self._lock:
            if not self.settings.rag_enabled:
                raise ValueError("向量检索未开启，请配置 RAG_ENABLED")
            if self._client is None:
                self.settings.require_uri()
                embedder = AliyunEmbedder(EmbeddingSettings())
                try:
                    client = create_milvus_client(self.settings)
                except Exception:
                    embedder.close()
                    raise
                self._client, self._embedder = client, embedder
            return self._client, self._embedder

    def _ensure(self, kind, *, create=False):
        client, embedder = self._resources()
        name = self.settings.milvus_schema_collection if kind == "schema" else self.settings.milvus_memory_collection
        with self._lock:
            if name not in self._ready:
                if not create and not client.has_collection(collection_name=name, timeout=self.settings.milvus_action_timeout_seconds):
                    return None
                ensure = ensure_schema_collection if kind == "schema" else ensure_memory_collection
                ensure(client, name=name, embedder=embedder, timeout=self.settings.milvus_action_timeout_seconds)
                self._ready.add(name)
        return client, embedder, name

    def search_schema(self, question, scope):
        ready = self._ensure("schema")
        if ready is None:
            return []
        client, embedder, name = ready
        return hybrid_search(client, collection=name, embedder=embedder, question=question,
                             expression="database_id == {database} and tenant_id == {tenant} and active == true",
                             parameters={"database": scope.database_id, "tenant": scope.tenant_id},
                             output_fields=["record_id", "schema_name", "table_name", "content_hash"], limit=8,
                             timeout=self.settings.milvus_action_timeout_seconds)

    def search_memory(self, question, scope):
        ready = self._ensure("memory")
        if ready is None:
            return []
        client, embedder, name = ready
        return hybrid_search(client, collection=name, embedder=embedder, question=question,
                             expression="database_id == {database} and tenant_id == {tenant} and owner_user_id == {owner} and active == true",
                             parameters={"database": scope.database_id, "tenant": scope.tenant_id, "owner": scope.owner_user_id},
                             output_fields=["memory_id"], limit=10, timeout=self.settings.milvus_action_timeout_seconds)

    def upsert_memory(self, memory):
        # An inactive record needs no new embedding; the SQLite visibility check is authoritative.
        ready = self._ensure("memory", create=bool(memory["active"]))
        if ready is None:
            return
        client, embedder, name = ready
        if not memory["active"]:
            client.delete(collection_name=name, ids=[memory["memory_id"]], timeout=self.settings.milvus_action_timeout_seconds)
            return
        row = {field: memory[field] for field in MEMORY_TEXT_FIELDS if field not in ("tables_json", "schema_fingerprints_json")}
        row["tables_json"] = json.dumps(memory["tables"], ensure_ascii=False)
        row["schema_fingerprints_json"] = json.dumps(memory["schema_fingerprints"], ensure_ascii=False, sort_keys=True)
        for field, limit in MEMORY_TEXT_FIELDS.items():
            if len(row[field].encode("utf-8")) > limit:
                raise ValueError(f"记忆字段 {field} 超过存储长度；原始确认记录仍保留")
        vector = embedder.encode_documents([memory["search_text"]]).dense[0]
        if len(vector) != embedder.dense_dim or not all(math.isfinite(v) for v in vector) or not any(vector):
            raise ValueError("记忆 Embedding 返回非法向量")
        row.update(active=True, dense_vector=vector)
        result = client.upsert(collection_name=name, data=[row], timeout=self.settings.milvus_action_timeout_seconds)
        if result.get("upsert_count") != 1:
            raise RuntimeError("记忆写入数量不匹配")

    def close(self):
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
            if self._embedder is not None:
                self._embedder.close()
                self._embedder = None
            self._ready.clear()
