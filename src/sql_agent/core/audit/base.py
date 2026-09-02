"""Audit logger stub."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sql_agent.core.audit.models import AuditEvent, AuditEventType

if TYPE_CHECKING:
    from sql_agent.core.tool.models import ToolCall, ToolContext, ToolResult
    from sql_agent.core.user.models import User


class AuditLogger(ABC):
    """Pluggable audit sink. Subclass and override log_event."""

    @abstractmethod
    async def log_event(self, event: AuditEvent) -> None: ...

    async def log_tool_access_check(
        self,
        user: "User",
        tool_name: str,
        access_granted: bool,
        required_groups: List[str],
        context: "ToolContext",
        reason: Optional[str] = None,
    ) -> None:
        await self.log_event(
            AuditEvent(
                event_type=AuditEventType.TOOL_ACCESS_CHECK,
                user_id=user.id,
                conversation_id=context.conversation_id,
                request_id=context.request_id,
                details={
                    "tool_name": tool_name,
                    "access_granted": access_granted,
                    "required_groups": required_groups,
                    "reason": reason,
                },
            )
        )

    async def log_tool_invocation(
        self,
        user: "User",
        tool_call: "ToolCall",
        context: "ToolContext",
    ) -> None:
        await self.log_event(
            AuditEvent(
                event_type=AuditEventType.TOOL_INVOCATION,
                user_id=user.id,
                conversation_id=context.conversation_id,
                request_id=context.request_id,
                details={
                    "tool_call_id": tool_call.id,
                    "tool_name": tool_call.name,
                    "arguments": tool_call.arguments,
                },
            )
        )

    async def log_tool_result(
        self,
        user: "User",
        tool_call: "ToolCall",
        result: "ToolResult",
        context: "ToolContext",
    ) -> None:
        await self.log_event(
            AuditEvent(
                event_type=AuditEventType.TOOL_RESULT,
                user_id=user.id,
                conversation_id=context.conversation_id,
                request_id=context.request_id,
                details={
                    "tool_call_id": tool_call.id,
                    "tool_name": tool_call.name,
                    "success": result.success,
                    "error": result.error,
                },
            )
        )


class NoOpAuditLogger(AuditLogger):
    """Discard all audit events."""

    async def log_event(self, event: AuditEvent) -> None:
        return None
