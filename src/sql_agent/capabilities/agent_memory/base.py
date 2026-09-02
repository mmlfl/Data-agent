"""Agent memory interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from sql_agent.core.tool.models import ToolContext


class AgentMemory(ABC):
    """Abstract base class for agent memory operations."""

    @abstractmethod
    async def save_tool_usage(
        self,
        question: str,
        tool_name: str,
        args: Dict[str, Any],
        context: "ToolContext",
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None: ...

    @abstractmethod
    async def search_similar_usage(
        self,
        question: str,
        context: "ToolContext",
        *,
        limit: int = 10,
        similarity_threshold: float = 0.7,
        tool_name_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def save_text_memory(self, content: str, context: "ToolContext") -> str: ...

    @abstractmethod
    async def clear_memories(self, context: "ToolContext") -> None: ...
