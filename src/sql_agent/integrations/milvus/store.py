from __future__ import annotations

from typing import Any

from pymilvus import MilvusClient

from sql_agent.integrations.milvus.client import create_milvus_client
from sql_agent.integrations.milvus.schema import ensure_dense_collection
from sql_agent.integrations.milvus.settings import MilvusSettings

_DEFAULT_SEARCH_PARAMS: dict[str, Any] = {"metric_type": "COSINE"}
_DEFAULT_OUTPUT_FIELDS = ["text", "database_id", "tenant_id", "active"]


def _require_scope_value(name: str, value: str | None) -> str:
    """scope 缺失时 fail-closed：宁可报错，也不带着 None 去过滤（会放宽或行为未定义）。"""
    if value is None:
        raise ValueError(f"scope 缺少 {name}，拒绝查询/删除")
    text = value.strip()
    if not text:
        raise ValueError(f"scope 的 {name} 为空，拒绝查询/删除")
    return text


class MilvusStore:
    """对某一个 Dense Collection 的通用读写搜（第 2 层）。

    不负责 health（连服务器探活）、不负责 RAG/业务语义。
    """

    def __init__(
        self,
        client: MilvusClient,
        *,
        collection_name: str,
        timeout: float,
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._timeout = timeout

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def ensure(self) -> None:
        """确保当前 Collection 存在（替代零散的 init）。"""
        ensure_dense_collection(
            self._client,
            collection_name=self._collection_name,
        )

    def ping(self) -> str:
        """可选：用已有 client 探版本。日常 health 仍建议独立函数。"""
        info = self._client.get_server_version(timeout=self._timeout)
        if isinstance(info, dict):
            return str(info.get("version", info))
        return str(info)

    def insert(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        self._client.insert(
            collection_name=self._collection_name,
            data=rows,
            timeout=self._timeout,
        )
        return len(rows)

    def upsert(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        self._client.upsert(
            collection_name=self._collection_name,
            data=rows,
            timeout=self._timeout,
        )
        return len(rows)

    def query(
        self,
        *,
        filter: str,
        filter_params: dict[str, Any] | None = None,
        output_fields: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        if not filter.strip():
            raise ValueError("query 必须提供非空 filter（避免误全表扫描）")

        kwargs: dict[str, Any] = {
            "collection_name": self._collection_name,
            "filter": filter,
            "output_fields": output_fields or _DEFAULT_OUTPUT_FIELDS,
            "timeout": self._timeout,
        }
        if filter_params is not None:
            kwargs["filter_params"] = filter_params
        if limit is not None:
            kwargs["limit"] = limit
        return self._client.query(**kwargs)

    def search(
        self,
        query_vectors: list[list[float]],
        *,
        limit: int = 5,
        filter: str | None = None,
        filter_params: dict[str, Any] | None = None,
        output_fields: list[str] | None = None,
        anns_field: str = "dense_vector",
        search_params: dict[str, Any] | None = None,
    ) -> list:
        if not query_vectors:
            return []

        kwargs: dict[str, Any] = {
            "collection_name": self._collection_name,
            "data": query_vectors,
            "anns_field": anns_field,
            "limit": limit,
            "output_fields": output_fields or _DEFAULT_OUTPUT_FIELDS,
            "search_params": search_params or _DEFAULT_SEARCH_PARAMS,
            "timeout": self._timeout,
        }
        if filter is not None:
            kwargs["filter"] = filter
            if filter_params is not None:
                kwargs["filter_params"] = filter_params
        return self._client.search(**kwargs)

    def search_in_scope(
        self,
        vectors: list[list[float]],
        *,
        database_id: str,
        tenant_id: str,
        limit: int = 5,
        output_fields: list[str] | None = None,
        anns_field: str = "dense_vector",
        search_params: dict[str, Any] | None = None,
    ) -> list:
        """组合：只在指定 database + tenant + active 范围内近邻搜索。"""
        database_id = _require_scope_value("database_id", database_id)
        tenant_id = _require_scope_value("tenant_id", tenant_id)
        return self.search(
            vectors,
            limit=limit,
            output_fields=output_fields,
            anns_field=anns_field,
            search_params=search_params,
            filter=(
                "database_id == $database_id and "
                "tenant_id == $tenant_id and "
                "active == true"
            ),
            filter_params={
                "database_id": database_id,
                "tenant_id": tenant_id,
            },
        )

    def delete(
        self,
        *,
        ids: list[str] | None = None,
        filter: str | None = None,
        filter_params: dict[str, Any] | None = None,
    ) -> None:
        if ids is None and filter is None:
            raise ValueError("delete 必须提供 ids 或 filter 之一")

        kwargs: dict[str, Any] = {
            "collection_name": self._collection_name,
            "timeout": self._timeout,
        }
        if ids is not None:
            kwargs["ids"] = ids
        if filter is not None:
            kwargs["filter"] = filter
            if filter_params is not None:
                kwargs["filter_params"] = filter_params
        self._client.delete(**kwargs)

    def delete_in_scope(
        self,
        *,
        database_id: str,
        tenant_id: str,
        ids: list[str] | None = None,
    ) -> int:
        """组合：先在 scope 内 query，再按 id 删除（避免跨租户误删）。

        兼容部分 PyMilvus 的 delete 不支持 filter_params 的情况。
        """
        database_id = _require_scope_value("database_id", database_id)
        tenant_id = _require_scope_value("tenant_id", tenant_id)
        rows = self.query(
            filter=(
                "database_id == $database_id and "
                "tenant_id == $tenant_id"
            ),
            filter_params={
                "database_id": database_id,
                "tenant_id": tenant_id,
            },
            output_fields=["id"],
        )
        allowed = {str(row["id"]) for row in rows}
        if ids is not None:
            allowed &= set(ids)
        if not allowed:
            return 0
        to_delete = list(allowed)
        self.delete(ids=to_delete)
        return len(to_delete)

    def close(self) -> None:
        self._client.close()

_settings = MilvusSettings()
store = MilvusStore(
    client=create_milvus_client(_settings),
    collection_name=_settings.milvus_collection_name,
    timeout=_settings.milvus_action_timeout_seconds
)