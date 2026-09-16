"""HTTP request/response models."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from sql_agent.components import UiComponent
from sql_agent.core.events import PROTOCOL_VERSION


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="User message")
    conversation_id: Optional[str] = Field(default=None)


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "sql-agent"
    protocol_version: Literal["1"] = PROTOCOL_VERSION
    with_db: bool = False
    db_dialect: str = "-"
    tools: list[str] = Field(default_factory=list)
    cache_status: Optional[str] = None
    cache_table_count: int = 0


class CacheSyncResponse(BaseModel):
    status: str
    dialect: str
    table_count: int
    message: str = ""


class ToolsResponse(BaseModel):
    tools: list[str]


class AgentEventDTO(BaseModel):
    protocol_version: Literal["1"] = PROTOCOL_VERSION
    type: str
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    ui_component: Optional[UiComponent] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
