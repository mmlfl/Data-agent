"""Server dependencies — singleton agent instance."""

from __future__ import annotations

from typing import Optional

from sql_agent.bootstrap import build_agent
from sql_agent.core.agent import Agent

_agent: Optional[Agent] = None


def get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent
