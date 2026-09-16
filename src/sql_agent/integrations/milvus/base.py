from __future__ import annotations

from sql_agent.integrations.milvus.client import create_milvus_client
from sql_agent.integrations.milvus.schema import ensure_dense_collection, mock_data
from sql_agent.integrations.milvus.settings import MilvusSettings

settings = MilvusSettings()
client = create_milvus_client(settings)

COLLECTION_NAME = "sql_agent_test_collection"

def health() -> None:
    try:
        info = client.get_server_version(
            detail=True,
            timeout=settings.milvus_connect_timeout_seconds,
        )
        print("uri:", settings.require_uri())
        print("server:", info)
        actual = str(info.get("version", "")) if isinstance(info, dict) else str(info)
        print("version:", actual)
    finally:
        return

def init_milvus()->None:
    print("starting init milvus...")
    try:
        ensure_dense_collection(client,collection_name=COLLECTION_NAME)
        print(f"collection {COLLECTION_NAME} created")
        print("has_collection",client.has_collection(COLLECTION_NAME))
        print("successfully init collection")
    except Exception as e:
        print(f"init milvus failed: {e}")
    finally:
        return

def shutdown_milvus() -> None:
    print("shutting down milvus...")
    try:
        client.close()
        print("successfully shutdown milvus...")
    except Exception as e:
        print(f"shutdown milvus failed: {e}")


if __name__ == "__main__":
    health()
    init_milvus()
    mock_data(client,collection_name=COLLECTION_NAME)
