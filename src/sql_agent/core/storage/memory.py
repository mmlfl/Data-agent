"""In-memory conversation store."""

from typing import Dict, List, Optional

from sql_agent.core.storage.base import ConversationStore
from sql_agent.core.storage.models import Conversation, Message
from sql_agent.core.user.models import User


class MemoryConversationStore(ConversationStore):
    """In-memory conversation store for local/dev use."""

    def __init__(self) -> None:
        self._conversations: Dict[str, Conversation] = {}

    async def create_conversation(
        self, conversation_id: str, user: User, initial_message: str
    ) -> Conversation:
        conversation = Conversation(
            id=conversation_id,
            user=user,
            messages=[Message(role="user", content=initial_message)],
        )
        self._conversations[conversation_id] = conversation
        return conversation

    async def get_conversation(
        self, conversation_id: str, user: User
    ) -> Optional[Conversation]:
        conversation = self._conversations.get(conversation_id)
        if conversation and conversation.user.id == user.id:
            return conversation
        return None

    async def update_conversation(self, conversation: Conversation) -> None:
        self._conversations[conversation.id] = conversation

    async def delete_conversation(self, conversation_id: str, user: User) -> bool:
        conversation = await self.get_conversation(conversation_id, user)
        if conversation:
            del self._conversations[conversation_id]
            return True
        return False

    async def list_conversations(
        self, user: User, limit: int = 50, offset: int = 0
    ) -> List[Conversation]:
        user_conversations = [
            conv for conv in self._conversations.values() if conv.user.id == user.id
        ]
        user_conversations.sort(key=lambda x: x.updated_at, reverse=True)
        return user_conversations[offset : offset + limit]
