"""HTTP request/response models."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="User message")
    conversation_id: Optional[str] = Field(default=None)


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "sql-agent"
    with_db: bool = False
    db_dialect: str = "-"
    tools: list[str] = Field(default_factory=list)


class ToolsResponse(BaseModel):
    tools: list[str]


class AgentEventDTO(BaseModel):
    type: str
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
