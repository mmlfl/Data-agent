"""Context token estimation for conversation window management."""

from __future__ import annotations

import json
from typing import Any, Optional, Sequence

from sql_agent.core.storage.models import Message
from sql_agent.core.llm.models import LlmRequest


def estimate_text_tokens(text: str) -> int:
    """Rough token estimate without a model-specific tokenizer.

    Heuristic tuned for mixed Chinese / English prompts:
    - CJK ideographs ≈ 1 token each
    - other characters ≈ 4 chars per token
    """
    if not text:
        return 0
    cjk = 0
    unicode_tokens = 0
    other = 0
    for ch in text:
        code = ord(ch)
        if (
            0x4E00 <= code <= 0x9FFF
            or 0x3400 <= code <= 0x4DBF
            or 0xF900 <= code <= 0xFAFF
            or 0x3000 <= code <= 0x303F
            or 0xFF00 <= code <= 0xFFEF
        ):
            cjk += 1
        elif code > 127:
            # Emoji, non-CJK scripts and combining marks are not ASCII words.
            unicode_tokens += len(ch.encode("utf-8"))
        else:
            other += 1
    return max(1, cjk + unicode_tokens + (other + 3) // 4)


def _json_size(value: Any) -> int:
    try:
        return estimate_text_tokens(
            json.dumps(value, ensure_ascii=False, default=str)
        )
    except (TypeError, ValueError):
        return estimate_text_tokens(str(value))


def estimate_message_tokens(message: Message) -> int:
    """Estimate tokens for one conversation message (content + tool payloads)."""
    total = 4  # role / framing overhead
    if message.content:
        total += estimate_text_tokens(message.content)
    if message.reasoning_content:
        total += estimate_text_tokens(message.reasoning_content)
    if message.tool_calls:
        for call in message.tool_calls:
            total += estimate_text_tokens(getattr(call, "name", "") or "")
            total += estimate_text_tokens(call.id)
            args = getattr(call, "arguments", None)
            if args is not None:
                total += _json_size(args)
            total += 6
    if message.tool_call_id:
        total += estimate_text_tokens(message.tool_call_id)
    return total


def estimate_context_tokens(
    *,
    system_prompt: Optional[str],
    messages: Sequence[Message],
) -> int:
    """Estimate tokens for system prompt + conversation history."""
    total = 0
    if system_prompt:
        total += estimate_text_tokens(system_prompt) + 4
    for message in messages:
        total += estimate_message_tokens(message)
    return total


def format_token_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".rstrip("0").rstrip(".")
    if n >= 10_000:
        return f"{n / 1000:.1f}K".rstrip("0").rstrip(".")
    if n >= 1000:
        return f"{n / 1000:.2f}K".rstrip("0").rstrip(".")
    return str(n)


def estimate_request_tokens(request: LlmRequest) -> int:
    """Include the enhanced messages and function schemas actually sent."""
    total = estimate_context_tokens(
        system_prompt=request.system_prompt, messages=request.messages
    )
    for tool in request.tools or []:
        total += _json_size({"type": "function", "function": {
            "name": tool.name, "description": tool.description,
            "parameters": tool.parameters,
        }}) + 8
    return total + 3


TRUNCATION_NOTICE = "\n[上下文限制：工具结果已截断，内容不完整。请缩小查询范围获取缺失数据，不要据此推断完整结果。]"


def truncate_tool_text(text: str, max_tokens: int) -> str:
    """Bound a preview by estimated tokens with one explicit omission marker."""
    if estimate_text_tokens(text) <= max_tokens:
        return text
    original = text.removesuffix(TRUNCATION_NOTICE)
    low, high = 0, len(original)
    while low < high:
        middle = (low + high + 1) // 2
        if estimate_text_tokens(original[:middle] + TRUNCATION_NOTICE) <= max_tokens:
            low = middle
        else:
            high = middle - 1
    return original[:low] + TRUNCATION_NOTICE


def is_context_overflow(error: Exception) -> bool:
    """Only retry explicit provider context errors, never generic rate limits."""
    code = str(getattr(error, "code", "") or "").lower()
    message = str(error).lower()
    return code in {"context_length_exceeded", "context_window_exceeded"} or any(
        marker in message for marker in (
            "context_length_exceeded", "maximum context length",
            "context window exceeded", "exceeds the context window",
        )
    )
