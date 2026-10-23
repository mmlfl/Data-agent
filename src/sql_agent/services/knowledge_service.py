"""Coordinate execution provenance, explicit feedback, relation paths and SQL examples."""

import logging
import threading

from sql_agent.capabilities.knoledge_store.experience_models import KnowledgeScope, SqlAnalysis, stable_hash
from sql_agent.retrieval.join_paths import find_join_path
from sql_agent.retrieval.relation_extractor import analyze_sql
from sql_agent.retrieval.schema_catalog import SchemaCatalog, SchemaCatalogCache

logger = logging.getLogger(__name__)


class KnowledgeService:
    def __init__(self, store, *, cache_path, database_id, tenant_id, dialect, vectors):
        self.store = store
        self.cache_path = cache_path
        self.database_id = database_id
        self.tenant_id = tenant_id
        self.dialect = dialect
        self.vectors = vectors
        self._index_lock = threading.Lock()
        self._catalog_cache = SchemaCatalogCache(cache_path)

    def scope(self, user_id: str) -> KnowledgeScope:
        return KnowledgeScope(self.tenant_id, self.database_id, user_id)

    def catalog(self) -> SchemaCatalog:
        return self._catalog_cache.get()

    def record_execution(self, question, context, call, result):
        analysis, fingerprints = SqlAnalysis(), {}
        executed = result.metadata.get("sql") if result.success else None
        try:
            catalog = self.catalog()
            if executed:
                analysis = analyze_sql(executed, self.dialect, catalog)
                fingerprints = catalog.fingerprints(analysis.tables) if analysis.schema_complete else {}
        except Exception:
            # A metadata/knowledge failure must not discard the actual query result.
            logger.warning("Could not snapshot query schema for knowledge")
        standalone = call.arguments.get("question") or question
        if not isinstance(standalone, str) or not standalone.strip():
            standalone = question
        return self.store.record_run(self.scope(context.user.id), request_id=context.request_id,
                                     tool_call_id=call.id, success=result.success,
                                     payload={"original_question": question, "standalone_question": standalone.strip(),
                                              "conversation_id": context.conversation_id,
                                              "requested_sql": call.arguments.get("sql", ""), "executed_sql": executed,
                                              "dialect": self.dialect, "tables": analysis.tables,
                                              "schema_fingerprints": fingerprints,
                                              "error_code": result.metadata.get("error_code"),
                                              "row_count": result.metadata.get("row_count"),
                                              "execution_time_ms": result.metadata.get("execution_time_ms"),
                                              "system_row_limit": result.metadata.get("system_row_limit", 100),
                                              "query_plan": result.metadata.get("query_plan")})

    def complete_request(self, user_id, request_id, query_id):
        self.store.mark_final(self.scope(user_id), request_id, query_id)

    def feedback(self, query_id, user_id, verdict):
        scope = self.scope(user_id)
        run = self.store.query(query_id, scope)
        analysis = SqlAnalysis()
        if verdict == "satisfied":
            try:
                catalog = self.catalog()
                if catalog.compatible(run["payload"].get("schema_fingerprints", {})):
                    analysis = analyze_sql(run["payload"]["executed_sql"], self.dialect, catalog)
                else:
                    analysis.skipped.append("元数据已变化或快照不完整，保留 SQL 样例，暂不发布连接规则")
            except Exception:
                analysis.skipped.append("连接结构暂不支持解析；SQL 样例仍保存")
        return self.store.feedback(query_id, scope, verdict, analysis)

    def feedback_status(self, query_id, user_id):
        scope = self.scope(user_id)
        run = self.store.query(query_id, scope)
        memory = self.store.memory("sql:" + stable_hash([scope.values, query_id]), scope)
        return {"query_id": query_id, "verdict": run["feedback"],
                "question": run["payload"]["standalone_question"],
                "index_status": memory["index_status"] if memory else "not_required",
                "eligible": bool(run["success"] and run["is_final"])}

    def sync_memory(self, memory_id, user_id):
        # A delayed index task must read the latest confirmation before mutating vectors.
        with self._index_lock:
            return self._sync_memory(memory_id, user_id)

    def _sync_memory(self, memory_id, user_id):
        memory = self.store.memory(memory_id, self.scope(user_id))
        if memory is None or memory["index_status"] == "indexed":
            return "not_required"
        if not self.vectors.enabled:
            return "pending"
        try:
            if memory["active"] and not self.catalog().compatible(memory["schema_fingerprints"]):
                self.store.mark_index(memory, "failed", "SchemaMismatch")
                return "failed"
            self.vectors.upsert_memory(memory)
            self.store.mark_index(memory, "indexed")
            return "indexed"
        except Exception as error:
            self.store.mark_index(memory, "failed", type(error).__name__)
            logger.warning("Memory indexing deferred (%s)", type(error).__name__)
            return "failed"

    def retry_indexes(self, user_id):
        pending = self.store.pending(self.scope(user_id))
        statuses = [self.sync_memory(item["memory_id"], user_id) for item in pending]
        return {"processed": len(statuses), "indexed": statuses.count("indexed"),
                "failed": statuses.count("failed"), "pending": statuses.count("pending")}

    def search_schema(self, question, user_id):
        try:
            rows = self.vectors.search_schema(question, self.scope(user_id))
            catalog = self.catalog()
            keys = []
            for row in rows:
                try:
                    key = catalog.resolve(row["table_name"], row.get("schema_name") or None)
                    if key not in keys:
                        keys.append(key)
                except ValueError:
                    pass
            tables, omitted = self._bounded_tables(catalog, keys)
            return {"status": "found" if tables else "empty", "tables": tables, "missing_tables": omitted,
                    "schema_version": catalog.version,
                    "note": "结构取当前 SQLite 快照；向量结果用于定位表，不代表表间已有连接"}
        except Exception as error:
            return {"status": "unavailable", "tables": [], "error_type": type(error).__name__,
                    "message": "单表向量检索暂不可用，可继续用 list_tables / describe_table"}

    def search_memory(self, question, user_id):
        scope = self.scope(user_id)
        if not self.store.has_active_memory(scope):
            return {"status": "empty", "examples": [], "message": "尚无用户确认的 SQL 样例"}
        try:
            rows = self.vectors.search_memory(question, scope)
            catalog, examples, seen = self.catalog(), [], set()
            for row in rows:
                memory_id = row.get("memory_id")
                if not memory_id or memory_id in seen:
                    continue
                seen.add(memory_id)
                memory = self.store.memory(memory_id, scope)
                if not memory or not memory["active"] or not catalog.compatible(memory["schema_fingerprints"]):
                    continue
                if len(memory["sql"]) > 12000:
                    continue  # Never return a silently truncated SQL example.
                examples.append({key: memory[key] for key in ("memory_id", "source_query_id", "question", "sql", "tables", "system_row_limit")})
                examples[-1]["query_plan"] = memory.get("query_plan")
                if len(examples) == 3:
                    break
            return {"status": "found" if examples else "empty", "examples": examples,
                    "note": "SQL 仅供参考：重新核对本题指标、粒度、日期及条件；标注的限行为系统安全上限，结果必须重新查询"}
        except Exception as error:
            return {"status": "unavailable", "examples": [], "error_type": type(error).__name__,
                    "message": "SQL 记忆索引暂不可用，可继续单表和关系工具"}

    @staticmethod
    def _bounded_tables(catalog, keys):
        import json
        tables, missing, used = [], [], 0
        for table in catalog.documents(keys):
            size = len(json.dumps(table, ensure_ascii=False))
            if not table["columns"] or used + size > 30000:
                missing.append(table["table_key"])
            else:
                tables.append(table)
                used += size
        return tables, missing

    def join_path(self, source, target, user_id, relation_ids=None):
        catalog = self.catalog()
        result = find_join_path(self.store, self.scope(user_id), catalog, source, target, relation_ids=relation_ids)
        if result["status"] == "found":
            result["tables"], result["missing_tables"] = self._bounded_tables(catalog, result["path"])
            result["schema_version"] = catalog.version
        for relation in result.get("relations", []) + result.get("candidates", []):
            for evidence in relation["sources"]:
                if len(evidence["source_sql"]) > 6000:
                    evidence["source_sql"] = evidence["source_sql"][:6000]
                    evidence["source_sql_truncated"] = True
                # Applicability may contain complete derived queries; bound it
                # explicitly rather than letting one rule exhaust the context.
                for key in ("source_fragment", "conditions"):
                    value = evidence.get(key)
                    text = "\n".join(value) if isinstance(value, list) else value
                    if text and len(text) > 6000:
                        evidence[key] = [text[:6000]] if isinstance(value, list) else text[:6000]
                        evidence[key + "_truncated"] = True
        return result

    def close(self):
        self._catalog_cache.close()
        self.vectors.close()
