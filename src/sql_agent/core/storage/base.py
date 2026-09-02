"""Conversation store abstract base class."""

from abc import ABC, abstractmethod
from typing import List, Optional

from sql_agent.core.storage.models import Conversation
from sql_agent.core.user.models import User


class ConversationStore(ABC):
    """Abstract base class for conversation storage."""

    @abstractmethod
    async def create_conversation(
        self, conversation_id: str, user: User, initial_message: str
    ) -> Conversation:
        """Create a new conversation with the specified ID."""

    @abstractmethod
    async def get_conversation(
        self, conversation_id: str, user: User
    ) -> Optional[Conversation]:
        """Get conversation by ID, scoped to user."""

    @abstractmethod
    async def update_conversation(self, conversation: Conversation) -> None:
        """Update conversation with new messages."""

    @abstractmethod
    async def delete_conversation(self, conversation_id: str, user: User) -> bool:
        """Delete conversation."""

    @abstractmethod
    async def list_conversations(
        self, user: User, limit: int = 50, offset: int = 0
    ) -> List[Conversation]:
        """List conversations for user."""
