"""Framework exception hierarchy."""


class AgentError(Exception):
    """Base exception for the agent framework."""


class ToolExecutionError(AgentError):
    """Error during tool execution."""


class ToolNotFoundError(AgentError):
    """Tool not found in registry."""


class PermissionError(AgentError):
    """User lacks required permissions."""


class ConversationNotFoundError(AgentError):
    """Conversation not found."""


class LlmServiceError(AgentError):
    """Error communicating with LLM service."""


class ValidationError(AgentError):
    """Data validation error."""
