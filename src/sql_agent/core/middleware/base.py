"""LLM request/response middleware."""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sql_agent.core.llm.models import LlmRequest, LlmResponse


class LlmMiddleware(ABC):
    """Intercept and transform LLM requests / responses. Default: passthrough."""

    async def before_llm_request(self, request: "LlmRequest") -> "LlmRequest":
        return request

    async def after_llm_response(
        self, request: "LlmRequest", response: "LlmResponse"
    ) -> "LlmResponse":
        return response
