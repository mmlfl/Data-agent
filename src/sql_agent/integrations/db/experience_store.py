"""Persistent, source-scoped confirmation ledger. Milvus is a rebuildable index."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
import uuid

from sql_agent.capabilities.knoledge_store.experience_models import KnowledgeScope, SqlAnalysis, stable_hash

SCOPE = "tenant_id=? AND database_id=? AND owner_user_id=?"


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class ExperienceStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS query_runs (
                    query_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, database_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL, request_id TEXT NOT NULL, tool_call_id TEXT NOT NULL,
                    success INTEGER NOT NULL, is_final INTEGER NOT NULL DEFAULT 0,
                    feedback TEXT, payload TEXT NOT NULL, created_at INTEGER NOT NULL,
                    UNIQUE(request_id, tool_call_id)
                );
                CREATE TABLE IF NOT EXISTS sql_memories (
                    memory_id TEXT PRIMARY KEY, source_query_id TEXT NOT NULL UNIQUE,
                    tenant_id TEXT NOT NULL, database_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
                    active INTEGER NOT NULL, index_status TEXT NOT NULL, content_hash TEXT NOT NULL,
                    payload TEXT NOT NULL, last_error TEXT, index_attempts INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS relation_edges (
                    relation_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, database_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL, left_table TEXT NOT NULL, right_table TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS relation_evidence (
                    relation_id TEXT NOT NULL, source_query_id TEXT NOT NULL,
                    active INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(relation_id, source_query_id)
                );
                CREATE INDEX IF NOT EXISTS idx_runs_scope ON query_runs(tenant_id,database_id,owner_user_id,request_id);
                CREATE INDEX IF NOT EXISTS idx_memory_scope ON sql_memories(tenant_id,database_id,owner_user_id,active);
                CREATE INDEX IF NOT EXISTS idx_memory_pending ON sql_memories(index_status);
                CREATE INDEX IF NOT EXISTS idx_relation_left ON relation_edges(tenant_id,database_id,owner_user_id,left_table);
                CREATE INDEX IF NOT EXISTS idx_relation_right ON relation_edges(tenant_id,database_id,owner_user_id,right_table);
                CREATE INDEX IF NOT EXISTS idx_evidence_source ON relation_evidence(source_query_id,active);
            """)
            if "index_attempts" not in {row["name"] for row in db.execute("PRAGMA table_info(sql_memories)")}:
                db.execute("ALTER TABLE sql_memories ADD COLUMN index_attempts INTEGER NOT NULL DEFAULT 0")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def record_run(self, scope: KnowledgeScope, *, request_id: str, tool_call_id: str,
                   success: bool, payload: dict) -> str:
        query_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO query_runs(query_id,tenant_id,database_id,owner_user_id,request_id,"
                       "tool_call_id,success,payload,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                       (query_id, *scope.values, request_id, tool_call_id, int(success), _json(payload), int(time.time())))
        return query_id

    def mark_final(self, scope: KnowledgeScope, request_id: str, query_id: str | None) -> None:
        with self.connect() as db:
            db.execute(f"UPDATE query_runs SET is_final=0 WHERE {SCOPE} AND request_id=?",
                       (*scope.values, request_id))
            if query_id:
                db.execute(f"UPDATE query_runs SET is_final=1 WHERE {SCOPE} AND request_id=? AND query_id=? AND success=1",
                           (*scope.values, request_id, query_id))

    def query(self, query_id: str, scope: KnowledgeScope) -> dict:
        with self.connect() as db:
            row = db.execute(f"SELECT * FROM query_runs WHERE {SCOPE} AND query_id=?", (*scope.values, query_id)).fetchone()
        if row is None:
            raise LookupError("未找到当前用户可确认的查询")
        return {**dict(row), "payload": json.loads(row["payload"])}

    def feedback(self, query_id: str, scope: KnowledgeScope, verdict: str, analysis: SqlAnalysis) -> dict:
        if verdict not in ("satisfied", "unsatisfied"):
            raise ValueError("不支持的反馈类型")
        memory_id = "sql:" + stable_hash([scope.values, query_id])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = db.execute(f"SELECT * FROM query_runs WHERE {SCOPE} AND query_id=?", (*scope.values, query_id)).fetchone()
            if run is None:
                raise LookupError("未找到当前用户可确认的查询")
            if not run["success"] or not run["is_final"]:
                raise ValueError("仅可反馈本轮最终成功查询")
            if run["feedback"] != verdict:
                db.execute("UPDATE query_runs SET feedback=? WHERE query_id=?", (verdict, query_id))
                active = verdict == "satisfied"
                if active:
                    payload = json.loads(run["payload"])
                    memory = {
                        "memory_id": memory_id, "source_query_id": query_id,
                        "tenant_id": scope.tenant_id, "database_id": scope.database_id, "owner_user_id": scope.owner_user_id,
                        "question": payload["standalone_question"], "sql": payload["executed_sql"],
                        "requested_sql": payload["requested_sql"], "search_text": payload["standalone_question"],
                        "tables": analysis.tables, "schema_fingerprints": payload.get("schema_fingerprints", {}),
                        "dialect": payload["dialect"], "system_row_limit": payload.get("system_row_limit"),
                        "query_plan": payload.get("query_plan"),
                        "relation_skipped": analysis.skipped,
                    }
                    digest = stable_hash(memory)
                    db.execute("INSERT INTO sql_memories(memory_id,source_query_id,tenant_id,database_id,owner_user_id,"
                               "active,index_status,content_hash,payload,last_error) VALUES (?,?,?,?,?,?,?,?,?,NULL) "
                               "ON CONFLICT(memory_id) DO UPDATE SET active=1,index_status='pending',"
                               "content_hash=excluded.content_hash,payload=excluded.payload,last_error=NULL",
                               (memory_id, query_id, *scope.values, 1, "pending", digest, _json(memory)))
                    for rule in analysis.relations:
                        relation_id = rule.identity(scope)
                        edge = {"relation_id": relation_id, "left_table": rule.left_table,
                                "right_table": rule.right_table, "key_pairs": rule.key_pairs}
                        db.execute("INSERT INTO relation_edges VALUES (?,?,?,?,?,?,?) ON CONFLICT(relation_id) DO NOTHING",
                                   (relation_id, *scope.values, rule.left_table, rule.right_table, _json(edge)))
                        evidence = {"source_query_id": query_id, "memory_id": memory_id,
                                    "source_fragment": rule.source_fragment, "source_sql": payload["executed_sql"],
                                    "conditions": rule.conditions, "join_type": rule.join_type,
                                    "relation_kind": rule.relation_kind, "aliases": rule.aliases,
                                    "join_direction": rule.join_direction,
                                    "extractor_version": 2,
                                    "schema_fingerprints": payload.get("schema_fingerprints", {})}
                        db.execute("INSERT INTO relation_evidence VALUES (?,?,1,?) ON CONFLICT(relation_id,source_query_id) "
                                   "DO UPDATE SET active=1,payload=excluded.payload", (relation_id, query_id, _json(evidence)))
                else:
                    db.execute("UPDATE sql_memories SET active=0,index_status='pending' WHERE source_query_id=?", (query_id,))
                    db.execute("UPDATE relation_evidence SET active=0 WHERE source_query_id=?", (query_id,))
            memory = db.execute("SELECT index_status,active FROM sql_memories WHERE memory_id=?", (memory_id,)).fetchone()
            count = db.execute("SELECT COUNT(*) FROM relation_evidence WHERE source_query_id=? AND active=1", (query_id,)).fetchone()[0]
        return {"query_id": query_id, "verdict": verdict, "memory_id": memory_id if memory else None,
                "index_status": memory["index_status"] if memory else "not_required",
                "relations": count, "relation_skipped": analysis.skipped}

    def memory(self, memory_id: str, scope: KnowledgeScope) -> dict | None:
        with self.connect() as db:
            row = db.execute(f"SELECT * FROM sql_memories WHERE {SCOPE} AND memory_id=?", (*scope.values, memory_id)).fetchone()
        return self._memory(row) if row else None

    @staticmethod
    def _memory(row) -> dict:
        return {**json.loads(row["payload"]), "active": bool(row["active"]),
                "content_hash": row["content_hash"], "index_status": row["index_status"],
                "index_attempts": row["index_attempts"]}

    def pending(self, scope: KnowledgeScope, limit: int = 20) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(f"SELECT * FROM sql_memories WHERE {SCOPE} AND index_status!='indexed' "
                              "ORDER BY CASE WHEN index_status='pending' THEN 0 ELSE 1 END,index_attempts,rowid LIMIT ?",
                              (*scope.values, min(max(limit, 1), 100))).fetchall()
        return [self._memory(row) for row in rows]

    def has_active_memory(self, scope: KnowledgeScope) -> bool:
        with self.connect() as db:
            return db.execute(f"SELECT 1 FROM sql_memories WHERE {SCOPE} AND active=1 LIMIT 1", scope.values).fetchone() is not None

    def mark_index(self, memory: dict, status: str, error: str | None = None) -> None:
        with self.connect() as db:
            db.execute("UPDATE sql_memories SET index_status=?,last_error=?,index_attempts=index_attempts+1 "
                       "WHERE memory_id=? AND content_hash=? AND active=?",
                       (status, error, memory["memory_id"], memory["content_hash"], int(memory["active"])))

    def neighbors(self, scope: KnowledgeScope, table: str, limit: int) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(f"SELECT * FROM relation_edges WHERE {SCOPE} AND (left_table=? OR right_table=?) "
                              "AND EXISTS(SELECT 1 FROM relation_evidence ev WHERE ev.relation_id=relation_edges.relation_id AND ev.active=1) "
                              "ORDER BY relation_id LIMIT ?", (*scope.values, table, table, limit)).fetchall()
            result = []
            for row in rows:
                evidence = db.execute("SELECT payload FROM relation_evidence WHERE relation_id=? AND active=1 ORDER BY rowid DESC LIMIT 11",
                                      (row["relation_id"],)).fetchall()
                result.append({**json.loads(row["payload"]), "sources": [json.loads(ev[0]) for ev in evidence[:10]],
                               "sources_truncated": len(evidence) > 10})
        return result
