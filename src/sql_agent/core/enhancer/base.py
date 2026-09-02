"""LLM context enhancer (dynamic prompt / message enrichment)."""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from sql_agent.core.llm.models import LlmMessage
    from sql_agent.core.user.models import User


class LlmContextEnhancer(ABC):
    """Dynamically enhance system prompt and messages (orthogonal to PromptBuilder)."""

    async def enhance_system_prompt(
        self, system_prompt: str, user_message: str, user: "User"
    ) -> str:
        return system_prompt

    async def enhance_user_messages(
        self, messages: List["LlmMessage"], user: "User"
    ) -> List["LlmMessage"]:
        return messages


class NoOpLlmContextEnhancer(LlmContextEnhancer):
    """Default enhancer that leaves prompts/messages unchanged."""
