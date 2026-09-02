"""Thread-safe SqlRunner pool (project extension; Vanna has no built-in pool)."""

from __future__ import annotations

import queue
import threading
from contextlib import contextmanager
from typing import Callable, Iterator

from sql_agent.capabilities.sql_runner import SqlRunner


class SqlRunnerPool:
    """Fixed-size pool of SqlRunner instances."""

    def __init__(
        self,
        factory: Callable[[], SqlRunner],
        pool_size: int = 5,
    ) -> None:
        self._factory = factory
        self._size = pool_size
        self._pool: queue.Queue[SqlRunner] = queue.Queue(maxsize=pool_size)
        self._all: list[SqlRunner] = []
        self._lock = threading.Lock()

        for _ in range(pool_size):
            self._pool.put(self._create())

    def _create(self) -> SqlRunner:
        runner = self._factory()
        runner.connect()
        with self._lock:
            self._all.append(runner)
        return runner

    def get(self, timeout: float = 30) -> SqlRunner:
        try:
            return self._pool.get(timeout=timeout)
        except queue.Empty as e:
            raise RuntimeError(
                f"连接池耗尽：{self._size} 个 SqlRunner 全部在用，等待 {timeout}s 超时"
            ) from e

    def put(self, runner: SqlRunner) -> None:
        runner.reset_transaction()
        try:
            alive = runner.is_alive()
        except Exception:
            alive = False
        if alive:
            self._pool.put(runner)
        else:
            runner.close()
            self._pool.put(self._create())

    @contextmanager
    def borrow(self, timeout: float = 30) -> Iterator[SqlRunner]:
        runner = self.get(timeout=timeout)
        try:
            yield runner
        finally:
            self.put(runner)

    def close(self) -> None:
        while not self._pool.empty():
            try:
                self._pool.get_nowait().close()
            except queue.Empty:
                break
        with self._lock:
            for runner in self._all:
                try:
                    runner.close()
                except Exception:
                    pass
            self._all.clear()

    @property
    def size(self) -> int:
        return self._size

    @property
    def available(self) -> int:
        return self._pool.qsize()

    def __enter__(self) -> "SqlRunnerPool":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# Backward-compatible alias
ConnectionPool = SqlRunnerPool
