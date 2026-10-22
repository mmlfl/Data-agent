"""Agent configuration."""

from typing import Optional

from pydantic import BaseModel, Field, model_validator


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
    auto_finalize_results: bool = Field(default=True)
    finalizer_tool_name: str = Field(default="finalize_result", min_length=1)
    max_finalize_rows: int = Field(default=20, gt=0, le=100)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, gt=0)
    # Hard context window: over limit → refresh (drop history), no compression.
    context_window_tokens: int = Field(default=256_000, gt=0)
    context_output_reserve_tokens: int = Field(default=4096, gt=0)
    context_safety_ratio: float = Field(default=0.05, ge=0, lt=0.5)
    audit_config: AuditConfig = Field(default_factory=AuditConfig)

    @model_validator(mode="after")
    def validate_context_budget(self):
        reserved = self.max_tokens or self.context_output_reserve_tokens
        if reserved + int(self.context_window_tokens * self.context_safety_ratio) >= self.context_window_tokens:
            raise ValueError("上下文窗口必须大于回答预留和估算安全余量之和")
        return self
