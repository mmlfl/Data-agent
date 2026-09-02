"""Observability models."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class Span(BaseModel):
    """Unit of work for tracing."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    start_time: float = Field(default_factory=time.time)
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    parent_id: Optional[str] = None

    def end(self) -> None:
        if self.end_time is None:
            self.end_time = time.time()

    def duration_ms(self) -> Optional[float]:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value


class Metric(BaseModel):
    """Metric measurement."""

    name: str
    value: float
    unit: str = ""
    tags: Dict[str, str] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
