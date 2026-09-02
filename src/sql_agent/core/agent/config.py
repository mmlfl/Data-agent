"""Agent configuration."""

from typing import Optional

from pydantic import BaseModel, Field


class AuditConfig(BaseModel):
    """Lightweight audit switches (no UI features)."""

    enabled: bool = True
    log_tool_access_checks: bool = True
    log_tool_invocations: bool = True
    log_tool_results: bool = True


class AgentConfig(BaseModel):
    """Configuration for agent behavior."""

    max_tool_iterations: int = Field(default=10, gt=0)
    stream_responses: bool = Field(default=True)
    auto_save_conversations: bool = Field(default=True)
    include_thinking_indicators: bool = Field(default=True)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, gt=0)
    audit_config: AuditConfig = Field(default_factory=AuditConfig)
