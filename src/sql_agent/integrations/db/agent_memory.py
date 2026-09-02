"""In-memory AgentMemory implementation."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sql_agent.capabilities.agent_memory.base import AgentMemory
from sql_agent.core.tool.models import ToolContext


class InMemoryAgentMemory(AgentMemory):
    """Simple list-backed memory for local development."""

    def __init__(self, max_items: int = 1000) -> None:
        self.max_items = max_items
        self._tool_usages: List[Dict[str, Any]] = []
        self._text_memories: List[Dict[str, Any]] = []

    async def save_tool_usage(
        self,
        question: str,
        tool_name: str,
        args: Dict[str, Any],
        context: ToolContext,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._tool_usages.append(
            {
                "id": str(uuid.uuid4()),
                "question": question,
                "tool_name": tool_name,
                "args": args,
                "success": success,
                "metadata": metadata or {},
                "user_id": context.user.id,
            }
        )
        if len(self._tool_usages) > self.max_items:
            self._tool_usages = self._tool_usages[-self.max_items :]

    async def search_similar_usage(
        self,
        question: str,
        context: ToolContext,
        *,
        limit: int = 10,
        similarity_threshold: float = 0.7,
        tool_name_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        q = question.lower()
        results: List[Dict[str, Any]] = []
        for item in reversed(self._tool_usages):
            if tool_name_filter and item["tool_name"] != tool_name_filter:
                continue
            if item["user_id"] != context.user.id:
                continue
            score = 1.0 if q and q in str(item["question"]).lower() else 0.0
            if score >= similarity_threshold or not q:
                results.append({**item, "score": score})
            if len(results) >= limit:
                break
        return results

    async def save_text_memory(self, content: str, context: ToolContext) -> str:
        memory_id = str(uuid.uuid4())
        self._text_memories.append(
            {"id": memory_id, "content": content, "user_id": context.user.id}
        )
        if len(self._text_memories) > self.max_items:
            self._text_memories = self._text_memories[-self.max_items :]
        return memory_id

    async def clear_memories(self, context: ToolContext) -> None:
        uid = context.user.id
        self._tool_usages = [m for m in self._tool_usages if m["user_id"] != uid]
        self._text_memories = [m for m in self._text_memories if m["user_id"] != uid]
