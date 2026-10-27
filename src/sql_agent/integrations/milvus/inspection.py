"""Explicit, scoped, read-only Milvus inspection. No ensure/load/embed/upsert."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import hashlib
import logging
import time
from types import SimpleNamespace

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from sql_agent.capabilities.knoledge_store.experience_models import stable_hash
from sql_agent.capabilities.knoledge_store.schema_documents import DOCUMENT_FORMAT, build_schema_document
from sql_agent.integrations.db.schema_cache import read_cached_schema_documents
from sql_agent.integrations.milvus.schema_collection import collection_incompatibility

SCAN_LIMIT = 5000
SUMMARY_FIELDS = ["record_id", "schema_name", "table_name", "column_count", "content_hash", "active", "updated_at"]
logger = logging.getLogger(__name__)


class InspectionProfile(BaseSettings):
    # Inspection does not require an Embedding API key or construct its client.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)
    model: str = Field(default="qwen3.7-text-embedding", validation_alias="EMBEDDING_MODEL")
    dimensions: int = Field(default=1024, gt=0, validation_alias="EMBEDDING_DIMENSIONS")


def _time(value):
    return datetime.fromtimestamp(int(value), timezone.utc).isoformat() if value else None


class MilvusInspection:
    def __init__(self, settings, db_settings, *, profile=None, client_factory=None):
        self.settings, self.db = settings, db_settings
        self.profile = profile or InspectionProfile()
        self.database_id = settings.rag_database_id.strip() or "db:" + stable_hash([
            db_settings.db_dialect, db_settings.db_host, db_settings.db_port,
            db_settings.db_database, db_settings.db_user])[:32]
        self.tenant_id = settings.rag_tenant_id
        self.collection = settings.milvus_schema_collection
        self.client_factory = client_factory

    def _base(self):
        return {"status": "not_configured", "message": "请先配置 MILVUS_URI。", "connected": False,
                "rag_enabled": self.settings.rag_enabled, "collection": self.collection,
                "milvus_database": self.settings.milvus_database,
                "database_id": self.database_id, "tenant_id": self.tenant_id,
                "collection_exists": None, "load_state": "未知", "can_browse": False,
                "document_count": None, "active_count": None, "vector_dimensions": None,
                "embedding_profile": None, "bm25": False, "issues": [], "indexes": [],
                "configured_embedding_profile": f"aliyun:{self.profile.model}:{self.profile.dimensions}",
                "matched_total": 0, "browse_total": 0, "truncated": False, "scan_limit": SCAN_LIMIT,
                "documents": [], "checked_at": datetime.now(timezone.utc).isoformat()}

    @contextmanager
    def _session(self):
        from pymilvus import MilvusClient
        settings = self.settings.model_copy(update={"milvus_connect_timeout_seconds": min(5, self.settings.milvus_connect_timeout_seconds)})
        if self.client_factory:
            client = self.client_factory(settings)
        else:
            # The sync client can create a database. Never reuse it here.
            kwargs = {"uri": settings.require_uri(), "db_name": settings.milvus_database,
                      "timeout": settings.milvus_connect_timeout_seconds}
            if settings.milvus_token:
                kwargs["token"] = settings.milvus_token
            client = MilvusClient(**kwargs)
        self._deadline = time.monotonic() + 25
        try:
            yield client
        finally:
            client.close()

    def _call(self, client, method, **kwargs):
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("inspection deadline")
        return getattr(client, method)(collection_name=self.collection,
                                      timeout=min(5, remaining, self.settings.milvus_action_timeout_seconds), **kwargs)

    def _filter(self, q=""):
        expression = "database_id == {database} and tenant_id == {tenant}"
        values = {"database": self.database_id, "tenant": self.tenant_id}
        if q.strip():
            literal = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            expression += " and (table_name like {keyword} or schema_name like {keyword})"
            values["keyword"] = "%" + literal + "%"
        return expression, values

    def _count(self, client, expression, values):
        rows = self._call(client, "query", filter=expression, filter_params=values,
                          output_fields=["count(*)"], consistency_level="Strong")
        if not rows or "count(*)" not in rows[0]:
            raise ValueError("Milvus did not return a count")
        return int(rows[0]["count(*)"])

    def _metadata(self, client, result):
        result["connected"] = True
        exists = self._call(client, "has_collection")
        result["collection_exists"] = exists
        if not exists:
            result.update(status="missing_collection", message="已连接 Milvus，但单表 Collection 尚未创建。")
            return
        actual = self._call(client, "describe_collection")
        fields = {field["name"]: field for field in actual.get("fields", [])}
        result["vector_dimensions"] = int((fields.get("dense_vector", {}).get("params") or {}).get("dim") or 0) or None
        try:
            description = actual.get("description") or "{}"
            description = json.loads(description) if isinstance(description, str) else description
            result["embedding_profile"] = description.get("embedding")
        except (ValueError, AttributeError):
            result["issues"].append("Collection 格式描述无法解析")
        indexes = {}
        for name in ("dense_idx", "sparse_idx"):
            try:
                indexes[name] = self._call(client, "describe_index", index_name=name)
                result["indexes"].append({"name": name, "field": indexes[name].get("field_name"),
                                           "metric": indexes[name].get("metric_type"),
                                           "type": indexes[name].get("index_type")})
            except Exception:
                indexes[name] = None
                result["issues"].append(f"未能读取索引 {name}")
        result["bm25"] = bool(indexes.get("sparse_idx") and indexes["sparse_idx"].get("metric_type") == "BM25")
        expected = SimpleNamespace(dense_dim=self.profile.dimensions,
                                   profile_id=f"aliyun:{self.profile.model}:{self.profile.dimensions}")
        if result["embedding_profile"] and result["embedding_profile"] != expected.profile_id:
            result["issues"].append("已有文档的 Embedding 配置与当前配置不同")
        try:
            reason = collection_incompatibility(actual, expected, indexes=indexes, row_count=0)
            if reason:
                result["issues"].append(reason)
        except (ValueError, TypeError, KeyError):
            result["issues"].append("Collection 定义与当前单表格式无法完整核对")
        state = self._call(client, "get_load_state").get("state")
        state = getattr(state, "name", str(state))
        result["load_state"] = state
        if state.lower().split(".")[-1] != "loaded":
            result.update(status="not_loaded", message="Collection 尚未加载，暂时无法查询文档；检查不会自动加载或修改它。")
            return
        required = set(SUMMARY_FIELDS) | {"database_id", "tenant_id", "document_text"}
        if not required.issubset(fields):
            result.update(status="incompatible", message="当前 Collection 缺少单表文档字段，不能按当前格式浏览。")
            return
        expression, values = self._filter()
        result["document_count"] = self._count(client, expression, values)
        result["active_count"] = self._count(client, expression + " and active == true", values)
        result.update(can_browse=True, status="warning" if result["issues"] else "ready",
                      message="Milvus 已连接，当前数据源文档可浏览。" if not result["issues"] else "文档可浏览，向量或索引配置存在待核对项。")

    def _local(self, keys=None):
        documents, invalid = {}, set()
        tables = read_cached_schema_documents(self.db.resolve_cache_path())
        for table in tables:
            key = (table.get("schema_name") or "", table["table_name"])
            if keys is not None and key not in keys:
                continue
            try:
                documents[key] = build_schema_document(table, database_id=self.database_id,
                    tenant_id=self.tenant_id, database_name=self.settings.rag_database_name, dialect=self.db.db_dialect)
            except ValueError:
                invalid.add(key)
        return documents, invalid

    @staticmethod
    def _comparison(row, local, invalid):
        key = (row["schema_name"], row["table_name"])
        if local is None:
            return "sqlite_unavailable"
        if key in invalid:
            return "sqlite_incomplete"
        if key not in local:
            return "sqlite_missing"
        if row["record_id"] != local[key].record_id:
            return "identity_mismatch"
        return "current" if row["content_hash"] == local[key].content_hash else "stale"

    def _rows(self, client, q=""):
        expression, values = self._filter(q)
        return self._call(client, "query", filter=expression, filter_params=values, output_fields=SUMMARY_FIELDS,
                          limit=SCAN_LIMIT + 1, consistency_level="Strong")

    def documents(self, q="", offset=0, limit=30):
        result = {**self._base(), "offset": offset, "limit": limit}
        if not self.settings.milvus_uri.strip():
            return result
        try:
            with self._session() as client:
                self._metadata(client, result)
                if not result["can_browse"]:
                    return result
                expression, values = self._filter(q)
                result["matched_total"] = self._count(client, expression, values) if q.strip() else result["document_count"]
                rows = self._rows(client, q)
                result["truncated"] = len(rows) > SCAN_LIMIT or result["matched_total"] > SCAN_LIMIT
                rows = sorted(rows[:SCAN_LIMIT], key=lambda r: (r["schema_name"], r["table_name"], r["record_id"]))
                result["browse_total"] = len(rows)
                page = rows[offset:offset + limit]
                try:
                    local, invalid = self._local({(r["schema_name"], r["table_name"]) for r in page})
                except Exception:
                    local, invalid = None, set()
                result["documents"] = [{**r, "updated_at": _time(r.get("updated_at")),
                                        "comparison": self._comparison(r, local, invalid)} for r in page]
        except Exception as error:
            logger.warning("Milvus document listing failed (%s)", type(error).__name__)
            result.update(status="unavailable", can_browse=False, document_count=None, active_count=None,
                          documents=[], message="暂时无法读取 Milvus，请检查连接、凭据及 Collection 权限后重试。")
        return result

    def document(self, record_id):
        result = self._base()
        if not self.settings.milvus_uri.strip():
            return {**result, "document": None}
        try:
            with self._session() as client:
                self._metadata(client, result)
                if not result["can_browse"]:
                    return {**result, "document": None}
                expression, values = self._filter()
                rows = self._call(client, "query", filter=expression + " and record_id == {record}",
                                  filter_params={**values, "record": record_id},
                                  output_fields=SUMMARY_FIELDS + ["document_text", "database_name", "dialect"],
                                  limit=1, consistency_level="Strong")
                if not rows:
                    return {**result, "status": "not_found", "message": "当前数据源中未找到该文档，请刷新列表。", "document": None}
                row = rows[0]
                row["content_hash_valid"] = hashlib.sha256((DOCUMENT_FORMAT + "\n" + row["document_text"]).encode("utf-8")).hexdigest() == row["content_hash"]
                try:
                    local, invalid = self._local({(row["schema_name"], row["table_name"])})
                except Exception:
                    local, invalid = None, set()
                return {**result, "document": {**row, "updated_at": _time(row.get("updated_at")),
                                              "comparison": self._comparison(row, local, invalid) if row["content_hash_valid"] else "invalid_hash"}}
        except Exception as error:
            logger.warning("Milvus document inspection failed (%s)", type(error).__name__)
            return {**result, "status": "unavailable", "can_browse": False, "document": None,
                    "document_count": None, "active_count": None,
                    "message": "无法读取该 Milvus 文档，请刷新后重试。"}

    def check(self):
        result = {**self._base(), "comparison": None}
        if not self.settings.milvus_uri.strip():
            return result
        try:
            with self._session() as client:
                self._metadata(client, result)
                if not result["can_browse"] and result["status"] != "missing_collection":
                    return result
                rows = self._rows(client) if result["can_browse"] else []
                complete = len(rows) <= SCAN_LIMIT and len(rows) == (result["document_count"] or 0)
                local, invalid = self._local()
                active = [r for r in rows[:SCAN_LIMIT] if r["active"]]
                remote_keys = {(r["schema_name"], r["table_name"]) for r in active}
                statuses = [self._comparison(r, local, invalid) for r in active]
                result["comparison"] = {"complete": complete, "scanned": min(len(rows), SCAN_LIMIT),
                    "sqlite_tables": len(local) + len(invalid), "matching": statuses.count("current"),
                    "stale": statuses.count("stale"), "sqlite_missing": statuses.count("sqlite_missing"),
                    "identity_mismatch": statuses.count("identity_mismatch"),
                    "duplicate_tables": len(active) - len(remote_keys),
                    "sqlite_incomplete": len(invalid), "inactive": sum(not r["active"] for r in rows[:SCAN_LIMIT]),
                    "milvus_missing": len(set(local) - remote_keys) if complete else None}
                result["comparison"]["consistent"] = result["can_browse"] and complete and not invalid and not result["issues"] and all(
                    result["comparison"][key] == 0 for key in ("stale", "sqlite_missing", "milvus_missing", "identity_mismatch", "duplicate_tables"))
        except Exception as error:
            logger.warning("Milvus consistency check failed (%s)", type(error).__name__)
            result.update(status="unavailable", can_browse=False, comparison=None,
                          document_count=None, active_count=None,
                          message="一致性检查未完成，请确认 Milvus 和本地 SQLite 均可读取。")
        return result
