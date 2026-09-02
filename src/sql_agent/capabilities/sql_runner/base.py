"""SQL runner capability interface.

Aligned with Vanna's capabilities.sql_runner.SqlRunner naming.
Extended with connection pooling / schema helpers used by this project.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Tuple


class SqlRunner(ABC):
    """Interface for SQL execution with different database implementations."""

    connection: Any

    @abstractmethod
    def connect(self) -> Any:
        """Open underlying driver connection."""

    @abstractmethod
    def close(self) -> None:
        """Close connection."""

    @abstractmethod
    def reset_transaction(self) -> None:
        """Rollback / clear transaction state before returning to pool."""

    @abstractmethod
    def is_alive(self) -> bool:
        """Health check."""

    @abstractmethod
    def ensure_connection(self) -> None:
        """Reconnect if dead."""

    @abstractmethod
    def begin_readonly(self, cursor: Any) -> None:
        """Enter a read-only transaction."""

    @abstractmethod
    def execute_readonly(self, sql: str) -> Tuple[List[str], List[tuple]]:
        """Execute read-only SQL; return (columns, rows)."""

    @abstractmethod
    def search_tables(self, keyword: str) -> List[dict]:
        """Search tables by name or comment (live on DB)."""

    @abstractmethod
    def describe_table(self, table_name: str) -> List[dict]:
        """Return column metadata for a table (live on DB)."""

    @abstractmethod
    def fetch_schema_metadata(self) -> Tuple[List[tuple], List[tuple]]:
        """Full schema dump for cache sync.

        tables: (table_name, schema_name, table_comment)
        columns: (table_name, column_name, data_type, nullable, data_length, column_comment)
        """
