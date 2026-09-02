"""Error recovery strategy (default: FAIL immediately)."""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

from sql_agent.core.recovery.models import RecoveryAction, RecoveryActionType

if TYPE_CHECKING:
    from sql_agent.core.llm.models import LlmRequest
    from sql_agent.core.tool.models import ToolContext


class ErrorRecoveryStrategy(ABC):
    """Decide how to proceed after tool / LLM errors. Default: FAIL."""

    async def handle_tool_error(
        self, error: Exception, context: "ToolContext", attempt: int = 1
    ) -> RecoveryAction:
        return RecoveryAction(
            action=RecoveryActionType.FAIL, message=f"Tool error: {error}"
        )

    async def handle_llm_error(
        self, error: Exception, request: "LlmRequest", attempt: int = 1
    ) -> RecoveryAction:
        return RecoveryAction(
            action=RecoveryActionType.FAIL, message=f"LLM error: {error}"
        )


class FailFastRecoveryStrategy(ErrorRecoveryStrategy):
    """Explicit default strategy that always fails."""
