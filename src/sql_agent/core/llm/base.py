"""LLM service abstract base class."""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, List

from sql_agent.core.llm.models import LlmRequest, LlmResponse, LlmStreamChunk


class LlmService(ABC):
    """Service for LLM communication."""

    @abstractmethod
    async def send_request(self, request: LlmRequest) -> LlmResponse:
        """Send a non-streaming request to the LLM."""

    @abstractmethod
    async def stream_request(
        self, request: LlmRequest
    ) -> AsyncGenerator[LlmStreamChunk, None]:
        """Stream a request to the LLM."""
        raise NotImplementedError
        yield  # pragma: no cover

    @abstractmethod
    async def validate_tools(self, tools: List[Any]) -> List[str]:
        """Validate tool schemas and return any error messages."""
