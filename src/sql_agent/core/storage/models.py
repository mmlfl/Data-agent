"""Storage domain models."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from sql_agent.core.tool.models import ToolCall
from sql_agent.core.user.models import User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Message(BaseModel):
    """Single message in a conversation."""

    role: str = Field(description="Message role (user/assistant/system/tool)")
    content: str = Field(description="Message content")
    timestamp: datetime = Field(default_factory=_utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tool_calls: Optional[List[ToolCall]] = Field(default=None)
    tool_call_id: Optional[str] = Field(
        default=None, description="ID if this is a tool response"
    )


class Conversation(BaseModel):
    """Conversation containing multiple messages."""

    id: str = Field(description="Unique conversation identifier")
    user: User = Field(description="User this conversation belongs to")
    messages: List[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        self.updated_at = _utcnow()
