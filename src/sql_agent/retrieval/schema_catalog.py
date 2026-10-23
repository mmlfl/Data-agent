"""An immutable, source-scoped view of the existing SQLite metadata snapshot."""

from copy import deepcopy
from pathlib import Path
import sqlite3
import threading

from sql_agent.capabilities.knoledge_store.experience_models import stable_hash
from sql_agent.integrations.db.schema_cache import read_cached_schema_documents, read_schema_snapshot


class AmbiguousTableError(ValueError):
    pass


class SchemaCatalog:
    def __init__(self, tables: list[dict]):
        self.tables = {}
        self._names, self._qualified, self._columns = {}, {}, {}
        for table in tables:
            key = ".".join(filter(None, [table.get("schema_name"), table["table_name"]]))
            self.tables[key] = deepcopy(table)
            self._names.setdefault(table["table_name"].casefold(), []).append(key)
            self._qualified.setdefault(((table.get("schema_name") or "").casefold(), table["table_name"].casefold()), []).append(key)
            columns = {}
            for column in table["columns"]:
                columns.setdefault(column["name"].casefold(), []).append(column["name"])
            self._columns[key] = columns
        self._fingerprints = {key: stable_hash(table) for key, table in self.tables.items()}
        self.version = stable_hash(self._fingerprints)

    @classmethod
    def from_cache(cls, path):
        return cls(read_cached_schema_documents(path))

    def resolve(self, name: str, schema: str | None = None) -> str:
        if schema is None and "." in name:
            schema, name = name.rsplit(".", 1)
        matches = self._names.get(name.casefold(), []) if schema is None else self._qualified.get((schema.casefold(), name.casefold()), [])
        if len(matches) > 1:
            raise AmbiguousTableError(f"表身份不唯一，请明确 schema 和大小写：{name}")
        if not matches:
            raise ValueError(f"表不存在或身份不唯一：{name}")
        return matches[0]

    def column(self, table: str, name: str) -> str:
        matches = self._columns[table].get(name.casefold(), [])
        if len(matches) != 1:
            raise ValueError(f"字段不存在或身份不唯一：{table}.{name}")
        return matches[0]

    def fingerprints(self, names: list[str]) -> dict[str, str]:
        return {name: self._fingerprints[name] for name in names}

    def compatible(self, fingerprints: dict[str, str]) -> bool:
        return bool(fingerprints) and all(
            self._fingerprints.get(name) == digest
            for name, digest in fingerprints.items()
        )

    def documents(self, names: list[str]) -> list[dict]:
        return [{"table_key": name, **deepcopy(self.tables[name])} for name in names]


class SchemaCatalogCache:
    """A read-only monitor detects committed updates, including SQLite WAL writes."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        self._lock = threading.RLock()
        self._connection = None
        self._identity = None
        self._data_version = None
        self._catalog = None

    def get(self) -> SchemaCatalog:
        with self._lock:
            stat = self.path.stat()
            identity = (stat.st_dev, stat.st_ino)
            if self._connection is None or identity != self._identity:
                self.close()
                self._connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True,
                                                  timeout=10, check_same_thread=False)
                self._identity = identity
            conn = self._connection
            conn.execute("BEGIN")
            try:
                version = conn.execute("PRAGMA data_version").fetchone()[0]
                if self._catalog is None or version != self._data_version:
                    self._catalog = SchemaCatalog(read_schema_snapshot(conn))
                    self._data_version = version
                return self._catalog
            finally:
                conn.rollback()  # Never hold a snapshot/lock across requests.

    def close(self):
        with self._lock:
            if self._connection is not None:
                self._connection.close()
            self._connection, self._catalog, self._data_version = None, None, None
