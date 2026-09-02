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


def main() -> None:
    parser = argparse.ArgumentParser(description="SQL Agent")
    parser.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=["serve", "demo"],
        help="serve: FastAPI server (default); demo: CLI one-shot",
    )
    args = parser.parse_args()

    if args.command == "demo":
        run_cli_demo()
    else:
        run_api_server()


if __name__ == "__main__":
    main()
