"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sql_agent.servers.deps import warmup_runtime
from sql_agent.servers.routes import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 进程启动时即 ensure_ready / sync，避免“等第一个 /health 才建缓存”
    print("[startup] warming up agent + schema cache ...")
    bundle = await asyncio.to_thread(warmup_runtime)
    if bundle.cache_info:
        print(
            f"[startup] schema cache ready: {bundle.cache_info['status']} · "
            f"{bundle.cache_info['table_count']} tables"
        )
    else:
        print("[startup] WITH_DB=false — skipped schema cache")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="SQL Agent API",
        description="SQL Agent chat API with SSE streaming",
        version="0.1.0",
        lifespan=lifespan,
    )

    origins_raw = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )
    origins = [o.strip() for o in origins_raw.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app
