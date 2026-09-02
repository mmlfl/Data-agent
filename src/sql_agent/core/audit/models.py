"""Audit event models (simplified, no UI features)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditEventType(str, Enum):
    TOOL_ACCESS_CHECK = "tool_access_check"
    TOOL_INVOCATION = "tool_invocation"
    TOOL_RESULT = "tool_result"
    AI_RESPONSE = "ai_response"
    MESSAGE_RECEIVED = "message_received"


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: AuditEventType
    timestamp: datetime = Field(default_factory=_utcnow)
    user_id: str
    conversation_id: str = ""
    request_id: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)
