from typing import Any

from pymilvus import MilvusClient

from sql_agent.integrations.milvus.settings import MilvusSettings


def create_milvus_client(settings: MilvusSettings) -> MilvusClient:
    kwards: dict[str,Any] = {
        "uri": settings.milvus_uri,
        "db_name": settings.milvus_database,
        "timeout": settings.milvus_connect_timeout_seconds,
    }
    if settings.milvus_token:
        kwards["token"] = settings.milvus_token

    return MilvusClient(**kwards)
