"""Default system prompt for the SQL insight workbench."""

from __future__ import annotations

import os
from datetime import datetime
from typing import List, Optional

from sql_agent.core.system_prompt.base import SystemPromptBuilder
from sql_agent.core.tool.models import ToolSchema
from sql_agent.core.user.models import User


def _dialect_notes(dialect: str) -> str:
    key = (dialect or "dm").strip().lower()
    if key in ("mysql",):
        return (
            "当前库方言：MySQL。\n"
            "- 探查样例可用 `LIMIT 1`；正式业务查询不要随便加 LIMIT。\n"
            "- 不要使用达梦/Oracle 的 ROWNUM。"
        )
    return (
        "当前库方言：达梦（Dameng）。\n"
        "- 探查样例可用 `WHERE ROWNUM <= 1`；正式业务查询不要随便加 ROWNUM。\n"
        "- 不支持 MySQL 的 LIMIT。"
    )


class DefaultSystemPromptBuilder(SystemPromptBuilder):
    """SQL analysis prompt with dual-channel result semantics."""

    def __init__(
        self,
        base_prompt: Optional[str] = None,
        *,
        dialect: Optional[str] = None,
        max_result_rows: Optional[int] = None,
    ) -> None:
        self.base_prompt = base_prompt
        self.dialect = dialect or os.getenv("DB_DIALECT", "dm")
        self.max_result_rows = max_result_rows or int(
            os.getenv("DB_MAX_RESULT_ROWS", "500")
        )

    async def build_system_prompt(
        self, user: User, tools: List[ToolSchema]
    ) -> Optional[str]:
        if self.base_prompt is not None:
            return self.base_prompt

        today = datetime.now().strftime("%Y-%m-%d")
        tool_names = [t.name for t in tools]
        parts = [
            "你是数据库 SQL 分析助手，通过只读查询回答用户问题。",
            f"今天的日期是 {today}。",
            _dialect_notes(self.dialect),
            "",
            "## 结果双通道（重要）",
            "- run_sql 会把完整结果（服务端安全上限内）送给前端画布展示/导出。",
            "- 回给你的文本只是少量样本，用于继续推理，避免上下文爆炸。",
            "- 因此：正式查询不要为了「怕太多」而写 ROWNUM/LIMIT；让 WHERE 条件决定结果集。",
            f"- 服务端最多返回约 {self.max_result_rows} 行；若达到上限，工具结果会提示截断。",
            "- 仅在这两种情况限行：① 探查字段形态取 1 行；② 用户明确要求 Top N / 前几条。",
            "",
            "## 时间语义",
            "- 「最近 / 近期 / 最新」优先写成时间窗口 WHERE，而不是 ORDER BY + Top N。",
            "- 未指定时长时，默认最近 30 天（可用今天日期推算）。",
            "- 「本月 / 这个月 / 上个月 / 今年」必须用对应日期范围过滤。",
            "- 排序（如按开始日期倒序）可以保留，但不能用排序+限行代替时间条件。",
            "",
            "## 工作方式",
            "1. 用 list_tables / describe_table 定位表与字段，再写 SQL。",
            "2. 必要时先取 1 行确认真实数据形态，再写带业务条件的正式 SELECT。",
            "3. 只读 SELECT；禁止写操作与多语句拼接。",
            "4. 根据样本与总行数给出中文结论；细节让用户在画布中查看。",
        ]
        if tool_names:
            parts.append("")
            parts.append(f"可用工具：{', '.join(tool_names)}")
        return "\n".join(parts)
