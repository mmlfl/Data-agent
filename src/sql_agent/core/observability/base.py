"""Observability provider (NoOp by default)."""

from __future__ import annotations

from abc import ABC
from typing import Any, Dict, Optional

from sql_agent.core.observability.models import Span


class ObservabilityProvider(ABC):
    """Collect telemetry. Default methods are no-ops suitable for subclassing."""

    async def record_metric(
        self,
        name: str,
        value: float,
        unit: str = "",
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        return None

    async def create_span(
        self, name: str, attributes: Optional[Dict[str, Any]] = None
    ) -> Span:
        return Span(name=name, attributes=attributes or {})

    async def end_span(self, span: Span) -> None:
        span.end()


class NoOpObservabilityProvider(ObservabilityProvider):
    """Explicit no-op provider."""
