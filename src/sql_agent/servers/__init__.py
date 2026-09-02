"""HTTP server package."""

from sql_agent.servers.app import create_app

__all__ = ["create_app", "run_server"]


def run_server() -> None:
    """Start uvicorn (called from main.py)."""
    import os
    import socket
    import sys

    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    reload = os.getenv("API_RELOAD", "false").lower() == "true"

    bind_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex((bind_host, port)) == 0:
            print(
                f"错误: 端口 {port} 已被占用，无法启动服务。\n"
                f"  1) 结束占用进程: netstat -ano | findstr :{port}  然后 taskkill /PID <pid> /F\n"
                f"  2) 或在 .env 中改用其他端口: API_PORT=8001",
                file=sys.stderr,
            )
            raise SystemExit(1)

    uvicorn.run(
        "sql_agent.servers.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )
