"""Default system prompt builder — neutral, no domain workflow."""

from datetime import datetime
from typing import List, Optional

from sql_agent.core.system_prompt.base import SystemPromptBuilder
from sql_agent.core.tool.models import ToolSchema
from sql_agent.core.user.models import User


class DefaultSystemPromptBuilder(SystemPromptBuilder):
    """Generic assistant prompt listing available tools."""

    def __init__(self, base_prompt: Optional[str] = None) -> None:
        self.base_prompt = base_prompt

    async def build_system_prompt(
        self, user: User, tools: List[ToolSchema]
    ) -> Optional[str]:
        if self.base_prompt is not None:
            return self.base_prompt

        today = datetime.now().strftime("%Y-%m-%d")
        tool_names = [t.name for t in tools]
        parts = [
            f"You are a helpful AI assistant. Today's date is {today}.",
            "Use available tools when they help accomplish the user's goals.",
            "After tool results return, summarize clearly for the user.",
        ]
        if tool_names:
            parts.append(f"Available tools: {', '.join(tool_names)}")
        return "\n".join(parts)
