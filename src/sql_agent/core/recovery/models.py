"""Recovery action models."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class RecoveryActionType(str, Enum):
    RETRY = "retry"
    FAIL = "fail"
    FALLBACK = "fallback"
    SKIP = "skip"


class RecoveryAction(BaseModel):
    action: RecoveryActionType = Field(description="Type of recovery action")
    retry_delay_ms: Optional[int] = None
    fallback_value: Optional[Any] = None
    message: Optional[str] = None
