"""System prompt builder interface."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from sql_agent.core.tool.models import ToolSchema
    from sql_agent.core.user.models import User


class SystemPromptBuilder(ABC):
    """Build system prompts from user + available tools."""

    @abstractmethod
    async def build_system_prompt(
        self, user: "User", tools: List["ToolSchema"]
    ) -> Optional[str]:
        """Return system prompt string, or None."""
