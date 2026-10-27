"""Durable, source-scoped run/event and task ledger; no cloud dependencies."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
import uuid


class RuntimeStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, scope TEXT NOT NULL, owner TEXT NOT NULL,
                    conversation_id TEXT NOT NULL, question TEXT NOT NULL, status TEXT NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL,
                    updated_at REAL NOT NULL, error TEXT);
                CREATE INDEX IF NOT EXISTS idx_runs_owner ON runs(scope,owner,conversation_id,created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_turn ON runs(scope,owner,conversation_id)
                    WHERE status IN ('queued','running','cancelling');
                CREATE TABLE IF NOT EXISTS run_events (
                    run_id TEXT NOT NULL, seq INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(run_id,seq));
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, scope TEXT NOT NULL, owner TEXT NOT NULL, target TEXT NOT NULL,
                    status TEXT NOT NULL, stage TEXT NOT NULL, created_at REAL NOT NULL,
                    updated_at REAL NOT NULL, report TEXT, error TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON jobs(scope,target)
                    WHERE status IN ('queued','running');
                CREATE TABLE IF NOT EXISTS conversations (
                    scope TEXT NOT NULL, owner TEXT NOT NULL, id TEXT NOT NULL,
                    payload TEXT NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY(scope,owner,id));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def recover(self, scope):
        # Called once by the owning server process after startup, not on each read.
        with self.connect() as db:
            interrupted = db.execute("SELECT id,conversation_id FROM runs WHERE scope=? AND status IN ('queued','running','cancelling')", (scope,)).fetchall()
            db.execute("UPDATE runs SET status='interrupted',error='服务重启，运行已中断',updated_at=? WHERE scope=? AND status IN ('queued','running','cancelling')", (time.time(), scope))
            for row in interrupted:
                sequence = db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM run_events WHERE run_id=?', (row['id'],)).fetchone()[0]
                event = {'protocol_version': '1', 'type': 'done', 'metadata': {'run_id': row['id'], 'event_id': f"{row['id']}:{sequence}", 'sequence': sequence,
                    'conversation_id': row['conversation_id'], 'terminal_state': 'interrupted'}}
                db.execute('INSERT INTO run_events VALUES(?,?,?)', (row['id'], sequence, json.dumps(event)))
            db.execute("UPDATE jobs SET status='interrupted',stage='服务重启，任务需要重试',updated_at=? WHERE scope=? AND status='running'", (time.time(), scope))

    def start_run(self, run_id, scope, owner, conversation_id, question):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if old:
                if (old['scope'], old['owner'], old['conversation_id'], old['question']) != (scope, owner, conversation_id, question):
                    raise ValueError("运行标识已用于其他请求")
                return False
            try:
                db.execute("INSERT INTO runs VALUES (?,?,?,?,?,'queued',0,?,?,NULL)", (run_id, scope, owner, conversation_id, question, time.time(), time.time()))
            except sqlite3.IntegrityError as error:
                raise ValueError("该会话已有运行中的分析，请等待完成或请求取消") from error
        return True

    def run(self, run_id, scope, owner):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=? AND scope=? AND owner=?", (run_id, scope, owner)).fetchone()
        if not row:
            raise LookupError("当前用户未找到该运行")
        return dict(row)

    def event(self, run_id, payload):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            event = {**payload, 'metadata': {**payload.get('metadata', {}), 'run_id': run_id, 'event_id': f'{run_id}:{seq}', 'sequence': seq}}
            db.execute("INSERT INTO run_events VALUES(?,?,?)", (run_id, seq, json.dumps(event, ensure_ascii=False)))
            db.execute("UPDATE runs SET updated_at=? WHERE id=?", (time.time(), run_id))
        return event

    def events(self, run_id, after=0, limit=200):
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM run_events WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?", (run_id, after, limit)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def finish(self, run_id, status, error=None):
        with self.connect() as db:
            db.execute("UPDATE runs SET status=?,error=?,updated_at=? WHERE id=?", (status, error, time.time(), run_id))

    def finish_event(self, run_id, payload, status, error=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            sequence = db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM run_events WHERE run_id=?', (run_id,)).fetchone()[0]
            payload['metadata'].update(run_id=run_id, event_id=f'{run_id}:{sequence}', sequence=sequence)
            db.execute('INSERT INTO run_events VALUES(?,?,?)', (run_id, sequence, json.dumps(payload, ensure_ascii=False)))
            db.execute('UPDATE runs SET status=?,error=?,updated_at=? WHERE id=?', (status, error, time.time(), run_id))

    def cancel(self, run_id, scope, owner):
        self.run(run_id, scope, owner)
        with self.connect() as db:
            db.execute("UPDATE runs SET cancel_requested=1,status='cancelling' WHERE id=? AND status IN ('queued','running')", (run_id,))
        return self.run(run_id, scope, owner)

    def enqueue(self, scope, owner, target):
        if target == 'knowledge':
            target = 'knowledge:' + owner
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE scope=? AND target=? AND status IN ('queued','running')", (scope, target)).fetchone()
            if row:
                return dict(row)
            job_id, now = uuid.uuid4().hex, time.time()
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,'queued','等待执行',?,?,NULL,NULL)", (job_id, scope, owner, target, now, now))
            return dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def jobs(self, scope, owner):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM jobs WHERE scope=? AND owner=? ORDER BY created_at DESC LIMIT 30", (scope, owner)).fetchall()
        return [{**dict(row), 'report': json.loads(row['report']) if row['report'] else None} for row in rows]

    def claim(self, scope):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE scope=? AND status='queued' ORDER BY created_at LIMIT 1", (scope,)).fetchone()
            if row:
                db.execute("UPDATE jobs SET status='running',stage='正在执行',updated_at=? WHERE id=?", (time.time(), row['id']))
                return dict(row)

    def finish_job(self, job_id, report=None, error=None):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=?,stage=?,report=COALESCE(?,report),error=?,updated_at=? WHERE id=?", ('error' if error else 'success', '未完成' if error else '已完成', json.dumps(report, ensure_ascii=False) if report else None, error, time.time(), job_id))

    def job_progress(self, job_id, report):
        with self.connect() as db:
            db.execute("UPDATE jobs SET stage=?,report=?,updated_at=? WHERE id=? AND status='running'", (f"已处理 {report['written'] + report['skipped']} / {report['total']} 张表", json.dumps(report), time.time(), job_id))
