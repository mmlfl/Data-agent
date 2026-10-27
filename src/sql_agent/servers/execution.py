"""Owned server tasks survive browser disconnects and publish replayable events."""
import asyncio
import logging
import time
import os

logger = logging.getLogger(__name__)
TERMINAL = {'success', 'partial', 'error', 'cancelled', 'interrupted'}


class ExecutionManager:
    def __init__(self, runtime):
        self.runtime, self.ledger, self.scope = runtime, runtime.ledger, runtime.scope
        self.tasks = {}
        self.stopping = False
        self.worker = None
        self.lease = None

    async def start(self):
        self.lease = open(self.ledger.path.with_suffix('.worker.lock'), 'a+b')
        self.lease.seek(0); self.lease.write(b'1'); self.lease.flush(); self.lease.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.lease.close(); self.lease = None
            raise RuntimeError('运行库已有服务实例，请使用单个服务进程；不要使用多个 Uvicorn workers') from error
        await asyncio.to_thread(self.ledger.recover, self.scope)
        self.worker = asyncio.create_task(self._jobs())

    async def submit_run(self, run_id, owner, conversation_id, question, context):
        created = await asyncio.to_thread(self.ledger.start_run, run_id, self.scope, owner, conversation_id, question)
        if created:
            self.tasks[run_id] = asyncio.create_task(self._run(run_id, owner, conversation_id, question, context))
        return await asyncio.to_thread(self.ledger.run, run_id, self.scope, owner)

    async def _run(self, run_id, owner, conversation_id, question, context):
        status, error = 'success', None
        completion = None
        pending = ''
        flushed = checked = time.monotonic()
        cancelled = False
        await asyncio.to_thread(self.ledger.finish, run_id, 'running')
        stream = self.runtime.agent.send_message(context, question, conversation_id=conversation_id)
        try:
            async for event in stream:
                if time.monotonic() - checked >= .1:
                    state = await asyncio.to_thread(self.ledger.run, run_id, self.scope, owner)
                    cancelled, checked = bool(state['cancel_requested']), time.monotonic()
                if cancelled:
                    status = 'cancelled'
                    break
                if event.type == 'done':
                    completion = event.model_dump(mode='json')
                    continue
                if event.type == 'text_delta':
                    pending += event.content or ''
                    if time.monotonic() - flushed < .06 and len(pending) < 512:
                        continue
                    event = event.model_copy(update={'content': pending})
                    pending, flushed = '', time.monotonic()
                elif pending:
                    await asyncio.to_thread(self.ledger.event, run_id, {'protocol_version': '1', 'type': 'text_delta', 'content': pending})
                    pending = ''
                if event.type == 'error':
                    status, error = 'error', event.content
                payload = event.model_dump(mode='json')
                if event.type == 'done':
                    payload['metadata']['terminal_state'] = status
                await asyncio.to_thread(self.ledger.event, run_id, payload)
        except asyncio.CancelledError:
            status, error = 'interrupted', '服务停止，分析已中断'
        except Exception as failure:
            logger.warning('Run failed (%s)', type(failure).__name__)
            status, error = 'error', '分析未完成，请查看运行记录'
        finally:
            await stream.aclose()
            state = await asyncio.to_thread(self.ledger.run, run_id, self.scope, owner)
            if state['cancel_requested']:
                status = 'cancelled'
            if status == 'success' and completion is None:
                status, error = 'interrupted', '分析未返回业务终态'
            if pending:
                await asyncio.to_thread(self.ledger.event, run_id, {'protocol_version': '1', 'type': 'text_delta', 'content': pending})
            if error:
                await asyncio.to_thread(self.ledger.event, run_id, {'protocol_version': '1', 'type': 'error', 'content': error})
            completion = completion or {'protocol_version': '1', 'type': 'done', 'metadata': {}}
            if status == 'success' and any(completion['metadata'].get(key) for key in ('context_overflow_stopped', 'request_budget_stopped', 'tool_limit_stopped')):
                status = 'partial'
            completion['metadata'].update(conversation_id=conversation_id, terminal_state=status)
            if status != 'success':
                completion['metadata'].pop('query_id', None)
                request_id = completion['metadata'].get('request_id')
                if request_id and self.runtime.knowledge_service is not None:
                    await asyncio.to_thread(self.runtime.knowledge_service.complete_request, owner, request_id, None)
            await asyncio.to_thread(self.ledger.finish_event, run_id, completion, status, error)
            self.tasks.pop(run_id, None)

    async def _jobs(self):
        last_repair = 0
        while not self.stopping:
            if time.monotonic() - last_repair > 60:
                last_repair = time.monotonic()
                try:
                    await asyncio.to_thread(self._repair_indexes)
                except Exception as failure:
                    logger.warning('Pending index recovery deferred (%s)', type(failure).__name__)
            job = await asyncio.to_thread(self.ledger.claim, self.scope)
            if not job:
                await asyncio.sleep(1)
                continue
            try:
                if job['target'] == 'sqlite':
                    cache = self.runtime.schema_cache
                    if cache is None:
                        raise ValueError('未启用业务数据库，无法同步 SQLite')
                    report = await asyncio.to_thread(cache.ensure_ready, force=True)
                    self.runtime.cache_info = report
                    report = {**report, 'message': f"已同步 {report['table_count']} 张表"}
                elif job['target'] == 'milvus':
                    from sql_agent.integrations.milvus.sync_schema import execute_schema_sync
                    report = await asyncio.to_thread(execute_schema_sync, progress=lambda value: self.ledger.job_progress(job['id'], value))
                    report['message'] = f"写入 {report.get('written', 0)} 张表，跳过 {report.get('skipped', 0)} 张，停用 {report.get('deactivated', 0)} 张"
                    if not report.get('reconciliation_complete'):
                        report['message'] += '；旧表全量对账未完成，请查看检查页'
                else:
                    service = self.runtime.knowledge_service
                    if service is None:
                        raise ValueError('尚未启用知识服务')
                    if job['target'].startswith('knowledge:'):
                        report = await asyncio.to_thread(service.retry_indexes, job['owner'])
                    else:
                        result = await asyncio.to_thread(service.sync_memory, job['target'].removeprefix('memory:'), job['owner'])
                        if result == 'failed':
                            raise ValueError('索引未完成，请检查 Embedding / Milvus 配置后重试')
                        report = {'message': result}
                await asyncio.to_thread(self.ledger.finish_job, job['id'], report)
            except Exception as failure:
                from sql_agent.servers.routes import _schema_sync_detail
                from sql_agent.integrations.milvus.schema_store import SchemaSyncError
                from pydantic import ValidationError
                if isinstance(failure, ValidationError):
                    message = '配置校验失败：' + '; '.join(item['msg'] for item in failure.errors(include_input=False, include_url=False))
                else:
                    message = _schema_sync_detail(failure) if isinstance(failure, SchemaSyncError) else str(failure) if isinstance(failure, (ValueError, FileNotFoundError)) else '任务未完成，请检查连接和配置后重试'
                from dataclasses import asdict
                partial = asdict(failure.report) if isinstance(failure, SchemaSyncError) else None
                await asyncio.to_thread(self.ledger.finish_job, job['id'], report=partial, error=message)

    def _repair_indexes(self):
        service = self.runtime.knowledge_service
        if service is None or not service.vectors.enabled:
            return
        with service.store.connect() as db:
            owners = db.execute("SELECT DISTINCT owner_user_id FROM sql_memories WHERE tenant_id=? AND database_id=? AND index_status!='indexed' AND index_attempts<5 LIMIT 20", (service.tenant_id, service.database_id)).fetchall()
        for row in owners:
            self.ledger.enqueue(self.scope, row[0], 'knowledge')

    async def close(self):
        self.stopping = True
        if self.worker:
            # A blocking synchronization must finish its batch/driver cleanup.
            await self.worker
        if self.tasks:
            await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
        if self.lease:
            self.lease.close(); self.lease = None


_manager = None


def get_execution_manager():
    global _manager
    if _manager is None:
        from sql_agent.servers.deps import get_runtime
        _manager = ExecutionManager(get_runtime())
    return _manager
