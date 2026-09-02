"""Core framework package — extension points and primitives."""

from sql_agent.core.agent import Agent, AgentConfig, AuditConfig
from sql_agent.core.audit import AuditLogger, NoOpAuditLogger
from sql_agent.core.enhancer import LlmContextEnhancer, NoOpLlmContextEnhancer
from sql_agent.core.enricher import ToolContextEnricher
from sql_agent.core.errors import (
    AgentError,
    ConversationNotFoundError,
    LlmServiceError,
    PermissionError,
    ToolExecutionError,
    ToolNotFoundError,
    ValidationError,
)
from sql_agent.core.events import AgentEvent
from sql_agent.core.filter import ConversationFilter
from sql_agent.core.lifecycle import LifecycleHook
from sql_agent.core.llm import DeepSeekLlmService, LlmService
from sql_agent.core.middleware import LlmMiddleware
from sql_agent.core.observability import NoOpObservabilityProvider, ObservabilityProvider
from sql_agent.core.system_prompt import DefaultSystemPromptBuilder, SystemPromptBuilder
from sql_agent.core.recovery import ErrorRecoveryStrategy, FailFastRecoveryStrategy
from sql_agent.core.registry import ToolRegistry
from sql_agent.core.workflow import NoOpWorkflowHandler, WorkflowHandler, WorkflowResult

__all__ = [
    "Agent",
    "AgentConfig",
    "AgentError",
    "AgentEvent",
    "AuditConfig",
    "AuditLogger",
    "ConversationFilter",
    "ConversationNotFoundError",
    "DeepSeekLlmService",
    "DefaultSystemPromptBuilder",
    "ErrorRecoveryStrategy",
    "FailFastRecoveryStrategy",
    "LifecycleHook",
    "LlmContextEnhancer",
    "LlmMiddleware",
    "LlmService",
    "LlmServiceError",
    "NoOpAuditLogger",
    "NoOpLlmContextEnhancer",
    "NoOpObservabilityProvider",
    "NoOpWorkflowHandler",
    "ObservabilityProvider",
    "PermissionError",
    "SystemPromptBuilder",
    "ToolContextEnricher",
    "ToolExecutionError",
    "ToolNotFoundError",
    "ToolRegistry",
    "ValidationError",
    "WorkflowHandler",
    "WorkflowResult",
]
