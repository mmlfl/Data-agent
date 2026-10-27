from typing import Any

from pymilvus import MilvusClient

from sql_agent.integrations.milvus.settings import MilvusSettings


def _database_names(raw: Any) -> list[str]:
    if isinstance(raw, dict):
        raw = raw.get("db_names") or raw.get("databases") or []
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names


def create_milvus_client(settings: MilvusSettings) -> MilvusClient:
    """Connect to the Milvus database named by MILVUS_DATABASE, creating it if needed."""
    db_name = settings.milvus_database
    kwargs: dict[str, Any] = {
        "uri": settings.require_uri(),
        "timeout": settings.milvus_connect_timeout_seconds,
    }
    if settings.milvus_token:
        kwargs["token"] = settings.milvus_token

    root = MilvusClient(**kwargs)
    try:
        existing = _database_names(root.list_databases())
        if db_name not in existing:
            root.create_database(db_name=db_name)
    except Exception:
        root.close()
        raise
    if db_name == "default":
        return root
    root.close()
    return MilvusClient(**kwargs, db_name=db_name)
