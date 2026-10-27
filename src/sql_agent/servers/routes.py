"""FastAPI routes."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import sqlite3
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from sql_agent.core.events import PROTOCOL_VERSION
from sql_agent.core.user import RequestContext
from sql_agent.integrations.db import DbSettings
from sql_agent.servers.deps import get_agent, get_runtime, get_schema_cache
from sql_agent.servers.schemas import (
    CacheSyncResponse,
    CacheTablesResponse,
    CacheTableResponse,
    CacheCheckResponse,
    MilvusInspectionResponse,
    MilvusDocumentResponse,
    MilvusCheckResponse,
    ChatRequest,
    HealthResponse,
    MilvusSyncResponse,
    ToolsResponse,
    QueryFeedbackRequest,
    MetadataJobRequest,
)

async def authorize_session(request: Request):
    secret = os.getenv('SQL_AGENT_AUTH_SECRET', '')
    if secret:
        from sql_agent.core.user.session import SignedSessionResolver
        try:
            user = await SignedSessionResolver(secret).resolve_user(RequestContext(cookies=dict(request.cookies)))
        except PermissionError as error:
            raise HTTPException(401, '会话无效，请先登录') from error
        request.state.authenticated_user = user
        if (request.url.path.startswith('/api/cache') or request.url.path.startswith('/api/milvus')
                or request.url.path.startswith('/api/metadata')) and 'admin' not in user.group_memberships:
            raise HTTPException(403, '此操作需要元数据管理权限')


router = APIRouter(dependencies=[Depends(authorize_session)])
logger = logging.getLogger(__name__)


def _request_context(request: Request) -> RequestContext:
    return RequestContext(cookies=dict(request.cookies), headers=dict(request.headers),
                          remote_addr=request.client.host if request.client else None,
                          query_params=dict(request.query_params))


async def _knowledge_user(request: Request, *, mutation=False):
    if mutation and request.headers.get("x-requested-with") != "SQL-Insight-Workbench":
        raise HTTPException(status_code=403, detail="反馈请求未通过来源校验")
    runtime = get_runtime()
    service = runtime.knowledge_service
    if service is None:
        raise HTTPException(status_code=503, detail="尚未启用数据库查询知识")
    user = await runtime.agent.user_resolver.resolve_user(_request_context(request))
    return service, user


@router.get("/api/queries/{query_id}/feedback")
async def query_feedback_status(query_id: str, request: Request):
    service, user = await _knowledge_user(request)
    try:
        return await asyncio.to_thread(service.feedback_status, query_id, user.id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/api/queries/{query_id}/feedback")
async def query_feedback(query_id: str, body: QueryFeedbackRequest, request: Request, tasks: BackgroundTasks):
    service, user = await _knowledge_user(request, mutation=True)
    try:
        result = await asyncio.to_thread(service.feedback, query_id, user.id, body.verdict)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if result["memory_id"] and result["index_status"] != "indexed":
        from sql_agent.servers.execution import get_execution_manager
        manager = get_execution_manager()
        await asyncio.to_thread(manager.ledger.enqueue, manager.scope, user.id, 'memory:' + result['memory_id'])
    return result


@router.post("/api/knowledge/reindex")
async def retry_knowledge_index(request: Request, tasks: BackgroundTasks):
    service, user = await _knowledge_user(request, mutation=True)
    from sql_agent.servers.execution import get_execution_manager
    manager = get_execution_manager()
    job = await asyncio.to_thread(manager.ledger.enqueue, manager.scope, user.id, 'knowledge')
    return {"status": "queued", "limit": 20, "job_id": job['id']}


def _authorize_cache_sync(request: Request) -> None:
    """Require an intentional same-origin request and optional admin token."""
    if request.headers.get("x-requested-with") != "SQL-Insight-Workbench":
        raise HTTPException(status_code=403, detail="缓存同步请求未通过安全校验")
    expected = os.getenv("CACHE_SYNC_TOKEN")
    if getattr(request.state, 'authenticated_user', None) is not None:
        return
    if expected:
        provided = request.headers.get("x-cache-sync-token", "")
        if not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=403, detail="缓存同步凭据无效")


def _authorize_milvus_sync(request: Request) -> None:
    """Require an intentional same-origin request and optional admin token."""
    if request.headers.get("x-requested-with") != "SQL-Insight-Workbench":
        raise HTTPException(status_code=403, detail="Milvus 同步请求未通过安全校验")
    expected = os.getenv("MILVUS_SYNC_TOKEN")
    if getattr(request.state, 'authenticated_user', None) is not None:
        return
    if expected:
        provided = request.headers.get("x-milvus-sync-token", "")
        if not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=403, detail="Milvus 同步凭据无效")


def _schema_sync_detail(error: Exception) -> str:
    """Map a failed upsert into a user-facing message without leaking provider bodies."""
    cause = error.__cause__
    cause_text = str(cause or "")
    if "AllocationQuota.FreeTierOnly" in cause_text or "Free quota exhausted" in cause_text:
        return (
            "Milvus 已连通，但 Embedding 免费额度已用完。"
            "请到阿里云百炼控制台关闭「仅使用免费额度」或充值后再同步。"
        )
    stage = getattr(error, "stage", "")
    if stage == "Embedding":
        return "Milvus 已连通，表结构向量化失败。请检查 DASHSCOPE_API_KEY 与模型额度。"
    if stage:
        return f"Milvus 同步在{stage}阶段失败，请检查连接后重跑。"
    return "Milvus 同步中断，请检查连接后重跑。"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    runtime = get_runtime()
    agent = runtime.agent
    with_db = os.getenv("WITH_DB", "false").lower() == "true"
    dialect = DbSettings().db_dialect if with_db else "-"
    tools = await agent.tool_registry.list_tools()

    cache = runtime.schema_cache
    cache_status = runtime.cache_info.get("status") if runtime.cache_info else None
    cache_table_count = 0
    if cache is not None:
        cache_table_count = await asyncio.to_thread(cache.table_count)
        if cache_status is None:
            cache_ready = await asyncio.to_thread(cache.is_ready)
            cache_status = "ready" if cache_ready else "empty"

    return HealthResponse(
        with_db=with_db,
        db_dialect=dialect,
        tools=tools,
        cache_status=cache_status,
        cache_table_count=cache_table_count,
    )


@router.post("/api/cache/sync", status_code=202)
async def sync_schema_cache(request: Request):
    """Compatibility entry point; all writes share the durable job queue."""
    return await start_metadata_job(MetadataJobRequest(target='sqlite'), request)


@router.post("/api/milvus/sync", status_code=202)
async def sync_milvus_schema(request: Request):
    return await start_metadata_job(MetadataJobRequest(target='milvus'), request)


def _cache_browser():
    from sql_agent.integrations.db.cache_browser import CacheBrowser
    settings = DbSettings()
    # Reading metadata does not require constructing a runtime or connecting to
    # the business DB, even when WITH_DB is disabled.
    return CacheBrowser(settings.resolve_cache_path(), settings.db_dialect)


@router.get("/api/cache/tables", response_model=CacheTablesResponse)
async def cached_tables(q: str = Query("", max_length=200),
                        schema_name: str | None = Query(None, max_length=256),
                        offset: int = Query(0, ge=0, le=1_000_000),
                        limit: int = Query(30, ge=1, le=100)):
    try:
        return await asyncio.to_thread(_cache_browser().tables, q=q, schema_name=schema_name, offset=offset, limit=limit)
    except (sqlite3.Error, OSError) as error:
        logger.warning("Could not browse SQLite cache (%s)", type(error).__name__)
        raise HTTPException(status_code=503, detail="暂时无法读取本地缓存，请稍后刷新或检查缓存文件。") from error


@router.get("/api/cache/table", response_model=CacheTableResponse)
async def cached_table(table_name: str = Query(min_length=1, max_length=256),
                       schema_name: str | None = Query(None, max_length=256)):
    try:
        result = await asyncio.to_thread(_cache_browser().table, table_name, schema_name)
    except (sqlite3.Error, OSError) as error:
        logger.warning("Could not read cached table (%s)", type(error).__name__)
        raise HTTPException(status_code=503, detail="暂时无法读取缓存字段，请刷新列表后重试。") from error
    if result is None:
        raise HTTPException(status_code=404, detail="该表不在当前 SQLite 缓存中，请刷新列表。")
    return result


@router.get("/api/cache/check", response_model=CacheCheckResponse)
async def check_sqlite_cache():
    try:
        return await asyncio.to_thread(_cache_browser().check)
    except (sqlite3.Error, OSError) as error:
        raise HTTPException(status_code=503, detail="SQLite 检查未完成，请检查缓存文件是否可读取。") from error


def _milvus_inspector():
    from sql_agent.integrations.milvus.inspection import MilvusInspection
    from sql_agent.integrations.milvus.settings import MilvusSettings
    return MilvusInspection(MilvusSettings(), DbSettings())


@router.get("/api/milvus/documents", response_model=MilvusInspectionResponse)
async def milvus_documents(q: str = Query("", max_length=200), offset: int = Query(0, ge=0, le=5000),
                           limit: int = Query(30, ge=1, le=100)):
    return await asyncio.to_thread(_milvus_inspector().documents, q, offset, limit)


@router.get("/api/milvus/document", response_model=MilvusDocumentResponse)
async def milvus_document(record_id: str = Query(min_length=1, max_length=128)):
    return await asyncio.to_thread(_milvus_inspector().document, record_id)


@router.get("/api/milvus/check", response_model=MilvusCheckResponse)
async def check_milvus_schema():
    return await asyncio.to_thread(_milvus_inspector().check)


@router.get("/api/tools", response_model=ToolsResponse)
async def list_tools() -> ToolsResponse:
    agent = get_agent()
    return ToolsResponse(tools=await agent.tool_registry.list_tools())


async def _runtime_user(request: Request):
    runtime = get_runtime()
    return await runtime.agent.user_resolver.resolve_user(_request_context(request))


@router.post('/api/metadata/jobs', status_code=202)
async def start_metadata_job(body: MetadataJobRequest, request: Request):
    if body.target == 'milvus':
        _authorize_milvus_sync(request)
    else:
        _authorize_cache_sync(request)
    from sql_agent.servers.execution import get_execution_manager
    manager, user = get_execution_manager(), await _runtime_user(request)
    return await asyncio.to_thread(manager.ledger.enqueue, manager.scope, user.id, body.target)


@router.get('/api/metadata/jobs')
async def metadata_jobs(request: Request):
    from sql_agent.servers.execution import get_execution_manager
    manager, user = get_execution_manager(), await _runtime_user(request)
    return {'jobs': await asyncio.to_thread(manager.ledger.jobs, manager.scope, user.id)}


@router.get('/api/runs/{run_id}')
async def run_status(run_id: str, request: Request, after: int = Query(0, ge=0)):
    from sql_agent.servers.execution import get_execution_manager
    manager, user = get_execution_manager(), await _runtime_user(request)
    try:
        run = await asyncio.to_thread(manager.ledger.run, run_id, manager.scope, user.id)
    except LookupError as error:
        raise HTTPException(404, '未找到当前用户的运行') from error
    return {**run, 'events': await asyncio.to_thread(manager.ledger.events, run_id, after)}


@router.post('/api/runs/{run_id}/cancel')
async def cancel_run(run_id: str, request: Request):
    if request.headers.get('x-requested-with') != 'SQL-Insight-Workbench':
        raise HTTPException(403, '请求来源无效')
    from sql_agent.servers.execution import get_execution_manager
    manager, user = get_execution_manager(), await _runtime_user(request)
    try:
        return await asyncio.to_thread(manager.ledger.cancel, run_id, manager.scope, user.id)
    except LookupError as error:
        raise HTTPException(404, '未找到当前用户的运行') from error


@router.get('/api/conversations')
async def conversations(request: Request):
    runtime, user = get_runtime(), await _runtime_user(request)
    def read():
        with runtime.ledger.connect() as db:
            rows = db.execute('SELECT conversation_id,MIN(created_at) first_seen,MAX(updated_at) updated_at FROM runs WHERE scope=? AND owner=? GROUP BY conversation_id ORDER BY updated_at DESC LIMIT 50', (runtime.scope, user.id)).fetchall()
            return [{'id': row['conversation_id'], 'title': db.execute('SELECT question FROM runs WHERE scope=? AND owner=? AND conversation_id=? ORDER BY created_at LIMIT 1', (runtime.scope, user.id, row['conversation_id'])).fetchone()[0][:100], 'updated_at': row['updated_at']} for row in rows]
    return {'conversations': await asyncio.to_thread(read)}


@router.get('/api/conversations/{conversation_id}/runs')
async def conversation_runs(conversation_id: str, request: Request):
    from sql_agent.servers.execution import get_execution_manager
    manager, user = get_execution_manager(), await _runtime_user(request)
    def read():
        with manager.ledger.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM runs WHERE scope=? AND owner=? AND conversation_id=? ORDER BY created_at', (manager.scope, user.id, conversation_id))]
    return {'runs': await asyncio.to_thread(read)}


@router.post("/api/chat")
async def chat_sse(body: ChatRequest, http_request: Request) -> StreamingResponse:
    from sql_agent.servers.execution import get_execution_manager, TERMINAL
    manager = get_execution_manager()
    user = await _runtime_user(http_request)
    request_context = RequestContext(
        cookies=dict(http_request.cookies),
        headers=dict(http_request.headers),
        remote_addr=http_request.client.host if http_request.client else None,
        query_params=dict(http_request.query_params),
    )

    run_id, conversation_id = body.run_id or uuid.uuid4().hex, body.conversation_id or uuid.uuid4().hex
    try:
        await manager.submit_run(run_id, user.id, conversation_id, body.message, request_context)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error

    async def generate() -> AsyncGenerator[str, None]:
        sequence = 0
        while True:
            events = await asyncio.to_thread(manager.ledger.events, run_id, sequence)
            for event in events:
                sequence = event['metadata']['sequence']
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event['type'] == 'done':
                    yield 'data: [DONE]\n\n'
                    return
            state = await asyncio.to_thread(manager.ledger.run, run_id, manager.scope, user.id)
            if state['status'] in TERMINAL and not events:
                # The terminal transaction may commit between reading events and state.
                if await asyncio.to_thread(manager.ledger.events, run_id, sequence):
                    continue
                terminal = {'protocol_version': '1', 'type': 'done', 'metadata': {
                    'run_id': run_id, 'conversation_id': state['conversation_id'], 'terminal_state': state['status']}}
                yield f"data: {json.dumps(terminal, ensure_ascii=False)}\n\n"
                yield 'data: [DONE]\n\n'
                return
            yield ': keepalive\n\n'
            await asyncio.sleep(.2)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
