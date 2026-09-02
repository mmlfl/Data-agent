"""FastAPI routes."""

from __future__ import annotations

import json
import os
import traceback
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from sql_agent.core.user import RequestContext
from sql_agent.integrations.db import DbSettings
from sql_agent.servers.deps import get_agent
from sql_agent.servers.schemas import (
    ChatRequest,
    HealthResponse,
    ToolsResponse,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    agent = get_agent()
    with_db = os.getenv("WITH_DB", "false").lower() == "true"
    dialect = DbSettings().db_dialect if with_db else "-"
    tools = await agent.tool_registry.list_tools()
    return HealthResponse(
        with_db=with_db,
        db_dialect=dialect,
        tools=tools,
    )


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
            traceback.print_exc()
            err = {"type": "error", "content": str(e), "metadata": {}}
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
