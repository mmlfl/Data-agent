"""Browse only the configured SQLite snapshot; never refresh from a business DB."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


def _time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).isoformat()
    except ValueError:
        return value


class CacheBrowser:
    def __init__(self, path, dialect):
        self.path, self.dialect = Path(path).resolve(), dialect

    @contextmanager
    def snapshot(self):
        conn = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN")
            yield conn
        finally:
            conn.close()

    def tables(self, *, q="", schema_name=None, offset=0, limit=30):
        result = {"available": self.path.is_file(), "cache_file": self.path.name,
                  "dialect": self.dialect, "total_tables": 0, "total_columns": 0,
                  "last_synced_at": None, "schemas": [], "matched_tables": 0,
                  "offset": offset, "limit": limit, "tables": []}
        if not result["available"]:
            return result
        clauses, parameters = [], []
        if q.strip():
            term = "%" + q.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
            clauses.append("""(t.table_name LIKE ? ESCAPE '!' OR t.table_comment LIKE ? ESCAPE '!'
                OR EXISTS(SELECT 1 FROM columns f WHERE f.table_name=t.table_name
                    AND (f.column_name LIKE ? ESCAPE '!' OR f.column_comment LIKE ? ESCAPE '!')))""")
            parameters.extend([term] * 4)
        if schema_name is not None:
            clauses.append("COALESCE(t.schema_name,'')=?")
            parameters.append(schema_name)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.snapshot() as conn:
            summary = conn.execute("SELECT COUNT(*),MAX(sync_time) FROM tables").fetchone()
            result.update(total_tables=summary[0], last_synced_at=_time(summary[1]),
                          total_columns=conn.execute("SELECT COUNT(*) FROM columns").fetchone()[0],
                          schemas=[r[0] for r in conn.execute("SELECT DISTINCT COALESCE(schema_name,'') FROM tables ORDER BY 1")],
                          matched_tables=conn.execute("SELECT COUNT(*) FROM tables t" + where, parameters).fetchone()[0])
            rows = conn.execute("""SELECT t.table_name,COALESCE(t.schema_name,'') schema_name,
                COALESCE(t.table_comment,'') table_comment,t.sync_time,
                (SELECT COUNT(*) FROM columns c WHERE c.table_name=t.table_name) column_count
                FROM tables t""" + where + " ORDER BY schema_name,t.table_name LIMIT ? OFFSET ?",
                (*parameters, limit, offset)).fetchall()
            result["tables"] = [{"table_name": r["table_name"], "schema_name": r["schema_name"],
                                 "table_comment": r["table_comment"], "column_count": r["column_count"],
                                 "synced_at": _time(r["sync_time"])} for r in rows]
        return result

    def table(self, table_name, schema_name=None):
        if not self.path.is_file():
            return None
        with self.snapshot() as conn:
            query, parameters = "SELECT * FROM tables WHERE table_name=?", [table_name]
            if schema_name is not None:
                query += " AND COALESCE(schema_name,'')=?"
                parameters.append(schema_name)
            table = conn.execute(query, parameters).fetchone()
            if table is None:
                return None
            columns = conn.execute("""SELECT column_name,data_type,column_comment,is_nullable,data_length
                FROM columns WHERE table_name=? ORDER BY id""", (table_name,)).fetchall()
            return {"table_name": table["table_name"], "schema_name": table["schema_name"] or "",
                    "table_comment": table["table_comment"] or "", "synced_at": _time(table["sync_time"]),
                    "columns": [dict(column) for column in columns]}

    def check(self):
        result = {"status": "missing", "message": "尚未找到本地 SQLite 缓存，请先同步。",
                  "cache_file": self.path.name, "checks": []}
        if not self.path.is_file():
            return result
        with self.snapshot() as conn:
            integrity = [row[0] for row in conn.execute("PRAGMA quick_check")]
            counts = conn.execute("SELECT COUNT(*) FROM tables").fetchone()[0]
            columns = conn.execute("SELECT COUNT(*) FROM columns").fetchone()[0]
            empty = conn.execute("SELECT COUNT(*) FROM tables t WHERE NOT EXISTS(SELECT 1 FROM columns c WHERE c.table_name=t.table_name)").fetchone()[0]
            orphan = conn.execute("SELECT COUNT(*) FROM columns c WHERE NOT EXISTS(SELECT 1 FROM tables t WHERE t.table_name=c.table_name)").fetchone()[0]
            duplicate = conn.execute("SELECT COALESCE(SUM(n-1),0) FROM (SELECT COUNT(*) n FROM columns GROUP BY table_name,column_name HAVING COUNT(*)>1)").fetchone()[0]
            checks = [
                {"label": "文件完整性", "ok": integrity == ["ok"], "detail": "通过" if integrity == ["ok"] else "未通过，请检查本地缓存文件"},
                {"label": "表与字段", "ok": counts > 0 and columns > 0, "detail": f"{counts} 张表 · {columns} 个字段"},
                {"label": "缺少字段的表", "ok": empty == 0, "detail": f"{empty} 张"},
                {"label": "孤立字段", "ok": orphan == 0, "detail": f"{orphan} 个"},
                {"label": "重复字段", "ok": duplicate == 0, "detail": f"{duplicate} 个"},
            ]
        healthy = all(item["ok"] for item in checks)
        return {**result, "status": "healthy" if healthy else "warning", "checks": checks,
                "message": "SQLite 缓存检查通过。" if healthy else "缓存存在待核对项，可查看下方检查结果。"}
