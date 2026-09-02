"""Conversation history filters."""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from sql_agent.core.storage.models import Message


class ConversationFilter(ABC):
    """Transform conversation history before it is sent to the LLM."""

    async def filter_messages(self, messages: List["Message"]) -> List["Message"]:
        return messages
