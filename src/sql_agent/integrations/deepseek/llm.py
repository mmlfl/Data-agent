"""DeepSeek LLM service via OpenAI SDK (Chat Completions + tools)."""

from __future__ import annotations

import json
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from sql_agent.core.llm.base import LlmService
from sql_agent.core.llm.models import LlmRequest, LlmResponse, LlmStreamChunk
from sql_agent.core.tool.models import ToolCall, ToolSchema

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


class DeepSeekLlmService(LlmService):
    """DeepSeek chat API using the official OpenAI-compatible endpoint."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **extra_client_kwargs: Any,
    ) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ImportError(
                "openai package is required. Install with: pip install openai"
            ) from e

        self.model = model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
        api_key = (
            api_key
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or "sk-placeholder"
        )
        base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL)

        client_kwargs: Dict[str, Any] = {**extra_client_kwargs}
        client_kwargs["api_key"] = api_key
        client_kwargs.setdefault(
            "timeout", float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
        )
        client_kwargs.setdefault(
            "max_retries", int(os.getenv("LLM_MAX_RETRIES", "2"))
        )
        if base_url:
            client_kwargs["base_url"] = base_url

        self._client = AsyncOpenAI(**client_kwargs)

    async def send_request(self, request: LlmRequest) -> LlmResponse:
        """Non-streaming Chat Completions request (includes tool schemas)."""
        payload = self._build_payload(request)
        resp = await self._client.chat.completions.create(**payload, stream=False)

        if not resp.choices:
            return LlmResponse(content=None, tool_calls=None, finish_reason=None)

        choice = resp.choices[0]
        content: Optional[str] = getattr(choice.message, "content", None)
        tool_calls = self._extract_tool_calls_from_message(choice.message)

        usage: Dict[str, int] = {}
        if getattr(resp, "usage", None):
            usage = {
                "prompt_tokens": int(getattr(resp.usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(
                    getattr(resp.usage, "completion_tokens", 0) or 0
                ),
                "total_tokens": int(getattr(resp.usage, "total_tokens", 0) or 0),
            }

        return LlmResponse(
            content=content,
            tool_calls=tool_calls or None,
            finish_reason=getattr(choice, "finish_reason", None),
            usage=usage or None,
        )

    async def stream_request(
        self, request: LlmRequest
    ) -> AsyncGenerator[LlmStreamChunk, None]:
        """Streaming Chat Completions; text deltas + final tool_calls chunk."""
        payload = self._build_payload(request)
        stream = await self._client.chat.completions.create(**payload, stream=True)

        tc_builders: Dict[int, Dict[str, Optional[str]]] = {}
        last_finish: Optional[str] = None

        async for event in stream:
            if not getattr(event, "choices", None):
                continue

            choice = event.choices[0]
            delta = getattr(choice, "delta", None)
            if delta is None:
                last_finish = getattr(choice, "finish_reason", last_finish)
                continue

            content_piece: Optional[str] = getattr(delta, "content", None)
            if content_piece:
                yield LlmStreamChunk(content=content_piece)

            streamed_tool_calls = getattr(delta, "tool_calls", None)
            if streamed_tool_calls:
                for tc in streamed_tool_calls:
                    idx = getattr(tc, "index", 0) or 0
                    builder = tc_builders.setdefault(
                        idx, {"id": None, "name": None, "arguments": ""}
                    )
                    if getattr(tc, "id", None):
                        builder["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn is not None:
                        if getattr(fn, "name", None):
                            builder["name"] = fn.name
                        if getattr(fn, "arguments", None):
                            builder["arguments"] = (builder["arguments"] or "") + (
                                fn.arguments or ""
                            )

            last_finish = getattr(choice, "finish_reason", last_finish)

        final_tool_calls: List[ToolCall] = []
        for builder in tc_builders.values():
            if not builder.get("name"):
                continue
            args_raw = builder.get("arguments") or "{}"
            try:
                loaded = json.loads(args_raw)
                args_dict: Dict[str, Any] = (
                    loaded if isinstance(loaded, dict) else {"args": loaded}
                )
            except Exception:
                args_dict = {"_raw": args_raw}
            final_tool_calls.append(
                ToolCall(
                    id=builder.get("id") or "tool_call",
                    name=builder["name"] or "tool",
                    arguments=args_dict,
                )
            )

        if final_tool_calls:
            yield LlmStreamChunk(
                tool_calls=final_tool_calls, finish_reason=last_finish
            )
        else:
            yield LlmStreamChunk(finish_reason=last_finish or "stop")

    async def validate_tools(self, tools: List[ToolSchema]) -> List[str]:
        errors: List[str] = []
        for tool in tools:
            if not tool.name or len(tool.name) > 64:
                errors.append(f"Invalid tool name: {tool.name!r}")
        return errors

    def _build_payload(self, request: LlmRequest) -> Dict[str, Any]:
        """Build OpenAI/DeepSeek payload: messages + tool JSON schemas."""
        messages: List[Dict[str, Any]] = []

        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})

        for msg in request.messages:
            item: Dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.role == "tool" and msg.tool_call_id:
                item["tool_call_id"] = msg.tool_call_id
            elif msg.role == "assistant" and msg.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(item)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}

        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in request.tools
            ]
            payload["tool_choice"] = "auto"

        return payload

    def _extract_tool_calls_from_message(self, message: Any) -> List[ToolCall]:
        tool_calls: List[ToolCall] = []
        for tc in getattr(message, "tool_calls", None) or []:
            fn = getattr(tc, "function", None)
            if not fn:
                continue
            args_raw = getattr(fn, "arguments", "{}")
            try:
                loaded = json.loads(args_raw)
                args_dict: Dict[str, Any] = (
                    loaded if isinstance(loaded, dict) else {"args": loaded}
                )
            except Exception:
                args_dict = {"_raw": args_raw}
            tool_calls.append(
                ToolCall(
                    id=getattr(tc, "id", "tool_call"),
                    name=getattr(fn, "name", "tool"),
                    arguments=args_dict,
                )
            )
        return tool_calls
