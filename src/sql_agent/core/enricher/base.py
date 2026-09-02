"""ToolContext enrichers."""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sql_agent.core.tool.models import ToolContext


class ToolContextEnricher(ABC):
    """Add data to ToolContext (usually via metadata) before tools run."""

    async def enrich_context(self, context: "ToolContext") -> "ToolContext":
        return context
