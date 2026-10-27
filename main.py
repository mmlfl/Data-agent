"""Entry point: CLI demo or FastAPI server."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def run_cli_demo() -> None:
    from sql_agent.bootstrap import build_agent
    from sql_agent.core.user import RequestContext
    from sql_agent.integrations.db import DbSettings

    with_db = os.getenv("WITH_DB", "false").lower() == "true"
    settings = DbSettings() if with_db else None
    dialect = settings.db_dialect if settings else "-"
    print(f"Building agent (with_db={with_db}, db_dialect={dialect}) ...")

    async def _demo() -> None:
        agent = build_agent(with_db=with_db)
        tools = await agent.tool_registry.list_tools()
        print(f"Registered tools: {tools}")
        print("Agent ready.\n")

        if not with_db:
            print(
                "未连接数据库（WITH_DB=false）。"
                "设置 WITH_DB=true 并配置 DB_* / DEEPSEEK_API_KEY 后可完整对话。"
            )
            return

        question = os.getenv("DEMO_QUESTION", "有哪些和用户相关的表？")
        print(f">>> {question}\n")
        async for event in agent.send_message(RequestContext(), question):
            prefix = f"[{event.type}]"
            if event.tool_name:
                prefix += f" {event.tool_name}"
            print(f"{prefix}: {event.content or ''}")

    asyncio.run(_demo())


def run_api_server() -> None:
    from sql_agent.servers import run_server

    host = os.getenv("API_HOST", "0.0.0.0")
    port = os.getenv("API_PORT", "8000")
    print(f"Starting SQL Agent API at http://{host}:{port}")
    print(f"  Health: http://127.0.0.1:{port}/health")
    print(f"  Chat SSE: POST http://127.0.0.1:{port}/api/chat")
    run_server()


def run_schema_sync(args: argparse.Namespace) -> None:
    """Only this explicit command creates embedding/Milvus resources."""
    import json

    from sql_agent.integrations.milvus.sync_schema import execute_schema_sync

    report = execute_schema_sync(
        cache_path=args.cache_path,
        database_id=args.database_id,
        database_name=args.database_name,
        tenant_id=args.tenant_id,
        collection=args.collection,
        table_names=args.table,
        refresh_cache=args.refresh_cache,
        dry_run=args.dry_run,
        force=args.force,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="SQL Agent")
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=["serve", "demo", "sync-schema"],
        help="serve: API; demo: CLI; sync-schema: SQLite 表结构写入 Milvus",
    )
    parser.add_argument("--cache-path", help="sync-schema: existing SQLite schema cache")
    parser.add_argument("--database-id", help="sync-schema: stable source database ID")
    parser.add_argument("--database-name", help="sync-schema: database display name")
    parser.add_argument("--tenant-id", help="sync-schema: source tenant, default local")
    parser.add_argument("--collection", help="sync-schema: formal dense + BM25 Collection")
    parser.add_argument("--table", action="append", help="sync-schema: exact table name; repeatable")
    parser.add_argument("--refresh-cache", action="store_true", help="sync-schema: first refresh SQLite from the business DB")
    parser.add_argument("--dry-run", action="store_true", help="sync-schema: validate local documents without cloud calls")
    parser.add_argument("--force", action="store_true", help="sync-schema: re-embed even unchanged documents")
    args = parser.parse_args()

    if args.command == "sync-schema":
        from pydantic import ValidationError
        from sql_agent.integrations.milvus.schema_store import SchemaSyncError
        try:
            run_schema_sync(args)
        except ValidationError as error:
            details = "; ".join(item["msg"] for item in error.errors(include_input=False, include_url=False))
            parser.exit(1, f"配置或文档校验失败：{details}\n")
        except (ValueError, FileNotFoundError, SchemaSyncError) as error:
            parser.exit(1, f"{error}\n")
        except Exception as error:
            # Provider/driver exception bodies can include secrets or submitted text.
            parser.exit(1, f"同步失败（{type(error).__name__}），请检查模型和 Milvus 连接配置。\n")
    elif args.command == "demo":
        run_cli_demo()
    else:
        run_api_server()


if __name__ == "__main__":
    main()
