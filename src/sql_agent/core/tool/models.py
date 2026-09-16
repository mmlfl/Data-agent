"""Tool domain models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from sql_agent.capabilities.agent_memory.base import AgentMemory
from sql_agent.components import UiComponent
from sql_agent.core.user.models import User


class ToolCall(BaseModel):
    """Represents a tool call from the LLM."""

    id: str = Field(description="Unique identifier for this tool call")
    name: str = Field(description="Name of the tool to execute")
    arguments: Dict[str, Any] = Field(description="Raw arguments from LLM")


class ToolContext(BaseModel):
    """Context passed to all tool executions."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    user: User
    conversation_id: str
    request_id: str = Field(description="Unique request identifier for tracing")
    agent_memory: AgentMemory = Field(
        description="Agent memory for tool usage learning"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Result from tool execution."""

    success: bool = Field(description="Whether execution succeeded")
    result_for_llm: str = Field(description="String content to send back to the LLM")
    ui_component: Optional[UiComponent] = Field(
        default=None, description="Structured rich representation for capable clients"
    )
    error: Optional[str] = Field(
        default=None, description="Internal diagnostic error; never expose directly"
    )
    user_error: Optional[str] = Field(
        default=None, description="Sanitized error safe to show to end users"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolSchema(BaseModel):
    """Schema describing a tool for LLM consumption."""

    name: str = Field(description="Tool name")
    description: str = Field(description="What this tool does")
    parameters: Dict[str, Any] = Field(description="JSON Schema of parameters")
    access_groups: List[str] = Field(
        default_factory=list, description="Groups permitted to access this tool"
    )


class ToolRejection(BaseModel):
    """Indicates tool execution should be rejected."""

    reason: str = Field(description="Explanation of why execution was rejected")
