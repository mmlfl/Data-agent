"""FastAPI routes."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse

from sql_agent.core.events import PROTOCOL_VERSION
from sql_agent.core.user import RequestContext
from sql_agent.integrations.db import DbSettings
from sql_agent.servers.deps import get_agent, get_runtime, get_schema_cache
from sql_agent.servers.schemas import (
    CacheSyncResponse,
    ChatRequest,
    HealthResponse,
    ToolsResponse,
    QueryFeedbackRequest,
)

router = APIRouter()
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
        tasks.add_task(service.sync_memory, result["memory_id"], user.id)
    return result


@router.post("/api/knowledge/reindex")
async def retry_knowledge_index(request: Request, tasks: BackgroundTasks):
    service, user = await _knowledge_user(request, mutation=True)
    tasks.add_task(service.retry_indexes, user.id)
    return {"status": "queued", "limit": 20}


def _authorize_cache_sync(request: Request) -> None:
    """Require an intentional same-origin request and optional admin token."""
    if request.headers.get("x-requested-with") != "SQL-Insight-Workbench":
        raise HTTPException(status_code=403, detail="缓存同步请求未通过安全校验")
    expected = os.getenv("CACHE_SYNC_TOKEN")
    if expected:
        provided = request.headers.get("x-cache-sync-token", "")
        if not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=403, detail="缓存同步凭据无效")


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


@router.post("/api/cache/sync", response_model=CacheSyncResponse)
async def sync_schema_cache(request: Request) -> CacheSyncResponse:
    """Force full schema sync into SQLite cache."""
    _authorize_cache_sync(request)
    cache = get_schema_cache()
    if cache is None:
        raise HTTPException(
            status_code=400,
            detail="未启用数据库（WITH_DB=false），无法同步 schema 缓存",
        )
    try:
        info = await asyncio.to_thread(cache.ensure_ready, force=True)
        # keep runtime.cache_info fresh
        runtime = get_runtime()
        runtime.cache_info = info
        return CacheSyncResponse(
            status=info["status"],
            dialect=info["dialect"],
            table_count=info["table_count"],
            message=f"已重新同步 {info['table_count']} 张表",
        )
    except Exception as e:
        logger.exception("Schema cache synchronization failed")
        raise HTTPException(
            status_code=500, detail="缓存同步失败，请检查数据库连接后重试"
        ) from e


@router.get("/api/tools", response_model=ToolsResponse)
async def list_tools() -> ToolsResponse:
    agent = get_agent()
    return ToolsResponse(tools=await agent.tool_registry.list_tools())


@router.post("/api/chat")
async def chat_sse(body: ChatRequest, http_request: Request) -> StreamingResponse:
    agent = get_agent()
    request_context = RequestContext(
        cookies=dict(http_request.cookies),
        headers=dict(http_request.headers),
        remote_addr=http_request.client.host if http_request.client else None,
        query_params=dict(http_request.query_params),
    )

    async def generate() -> AsyncGenerator[str, None]:
        try:
            async for event in agent.send_message(
                request_context,
                body.message,
                conversation_id=body.conversation_id,
            ):
                payload = event.model_dump()
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("Unhandled SSE chat failure")
            err = {
                "protocol_version": PROTOCOL_VERSION,
                "type": "error",
                "content": "分析连接异常中断，请稍后重试。",
                "metadata": {"error_code": "sse_stream_failed"},
            }
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
