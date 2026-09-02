"""Simple text / event stream models for Agent output."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AgentEvent(BaseModel):
    """Lightweight event yielded by Agent.send_message.

    type 常用值:
      - status: 状态提示
      - text_delta: 流式文本增量
      - text: 完整文本回复
      - tool_start: 开始执行工具
      - tool_result: 工具执行结果
      - error: 错误
      - done: 本轮结束
    """

    type: str = Field(description="Event type")
    content: Optional[str] = Field(default=None, description="Text payload")
    tool_name: Optional[str] = Field(default=None)
    tool_call_id: Optional[str] = Field(default=None)
    metadata: Dict[str, Any] = Field(default_factory=dict)
