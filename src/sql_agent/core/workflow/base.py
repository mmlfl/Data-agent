"""Workflow handler — short-circuit before LLM (uses AgentEvent, not UI)."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Awaitable, Callable, List, Optional

from sql_agent.core.events import AgentEvent

if TYPE_CHECKING:
    from sql_agent.core.agent.agent import Agent
    from sql_agent.core.storage.models import Conversation
    from sql_agent.core.user.models import User


@dataclass
class WorkflowResult:
    """Result of a workflow attempt."""

    should_skip_llm: bool
    events: List[AgentEvent] = field(default_factory=list)
    conversation_mutation: Optional[
        Callable[["Conversation"], Awaitable[None]]
    ] = None


class WorkflowHandler(ABC):
    """Deterministic pre-LLM workflow (commands, routing, etc.)."""

    async def try_handle(
        self,
        agent: "Agent",
        user: "User",
        conversation: "Conversation",
        message: str,
    ) -> WorkflowResult:
        return WorkflowResult(should_skip_llm=False)

    async def get_starter_events(
        self,
        agent: "Agent",
        user: "User",
        conversation: "Conversation",
    ) -> Optional[List[AgentEvent]]:
        """Optional starter events when a conversation begins. Default: None."""
        return None


class NoOpWorkflowHandler(WorkflowHandler):
    """Never short-circuits; always continues to the LLM."""
