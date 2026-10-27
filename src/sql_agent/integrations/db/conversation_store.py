"""SQLite conversation storage, bound to the same scope as the runtime ledger."""
import asyncio
import time
from sql_agent.core.storage.base import ConversationStore
from sql_agent.core.storage.models import Conversation, Message


class SqliteConversationStore(ConversationStore):
    def __init__(self, ledger, scope):
        self.ledger, self.scope = ledger, scope

    async def create_conversation(self, conversation_id, user, initial_message):
        conversation = Conversation(id=conversation_id, user=user, messages=[Message(role='user', content=initial_message)])
        await self.update_conversation(conversation)
        return conversation

    async def get_conversation(self, conversation_id, user):
        def read():
            with self.ledger.connect() as db:
                row = db.execute("SELECT payload FROM conversations WHERE scope=? AND owner=? AND id=?", (self.scope, user.id, conversation_id)).fetchone()
            return Conversation.model_validate_json(row[0]) if row else None
        return await asyncio.to_thread(read)

    async def update_conversation(self, conversation):
        def write():
            with self.ledger.connect() as db:
                db.execute("INSERT INTO conversations VALUES(?,?,?,?,?) ON CONFLICT(scope,owner,id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at", (self.scope, conversation.user.id, conversation.id, conversation.model_dump_json(), time.time()))
        await asyncio.to_thread(write)

    async def delete_conversation(self, conversation_id, user):
        def delete():
            with self.ledger.connect() as db:
                return db.execute("DELETE FROM conversations WHERE scope=? AND owner=? AND id=?", (self.scope, user.id, conversation_id)).rowcount > 0
        return await asyncio.to_thread(delete)

    async def list_conversations(self, user, limit=50, offset=0):
        def read():
            with self.ledger.connect() as db:
                rows = db.execute("SELECT payload FROM conversations WHERE scope=? AND owner=? ORDER BY updated_at DESC LIMIT ? OFFSET ?", (self.scope, user.id, limit, offset)).fetchall()
            return [Conversation.model_validate_json(row[0]) for row in rows]
        return await asyncio.to_thread(read)
