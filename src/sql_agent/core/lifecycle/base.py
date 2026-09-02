"""Lifecycle hooks for message / tool execution."""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from sql_agent.core.storage.models import Conversation
    from sql_agent.core.tool.base import Tool
    from sql_agent.core.tool.models import ToolContext, ToolResult
    from sql_agent.core.user.models import User


class LifecycleHook(ABC):
    """Hook into agent execution lifecycle. Override methods as needed."""

    async def before_message(self, user: "User", message: str) -> Optional[str]:
        """Called before processing a user message. Return modified text or None."""
        return None

    async def after_message(self, conversation: "Conversation") -> None:
        """Called after a message turn is fully processed."""
        return None

    async def before_tool(
        self, tool: "Tool[Any]", context: "ToolContext"
    ) -> None:
        """Called before tool execution. Raise AgentError to abort."""
        return None

    async def after_tool(
        self, result: "ToolResult"
    ) -> Optional["ToolResult"]:
        """Called after tool execution. Return modified result or None."""
        return None
