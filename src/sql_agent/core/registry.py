"""Tool registry for managing and executing tools."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, TypeVar, Union

from sql_agent.core.tool import (
    Tool,
    ToolCall,
    ToolContext,
    ToolRejection,
    ToolResult,
    ToolSchema,
)
from sql_agent.core.user import User

if TYPE_CHECKING:
    from sql_agent.core.agent.config import AuditConfig
    from sql_agent.core.audit import AuditLogger

T = TypeVar("T")


class _LocalToolWrapper(Tool[T]):
    """Wrapper that overrides access_groups at registration time."""

    def __init__(self, wrapped_tool: Tool[T], access_groups: List[str]) -> None:
        self._wrapped_tool = wrapped_tool
        self._access_groups = access_groups

    @property
    def name(self) -> str:
        return self._wrapped_tool.name

    @property
    def description(self) -> str:
        return self._wrapped_tool.description

    @property
    def access_groups(self) -> List[str]:
        return self._access_groups

    def get_args_schema(self) -> Type[T]:
        return self._wrapped_tool.get_args_schema()

    async def execute(self, context: ToolContext, args: T) -> ToolResult:
        return await self._wrapped_tool.execute(context, args)


class ToolRegistry:
    """Registry for managing tools."""

    def __init__(
        self,
        audit_logger: Optional["AuditLogger"] = None,
        audit_config: Optional["AuditConfig"] = None,
    ) -> None:
        self._tools: Dict[str, Tool[Any]] = {}
        self.audit_logger = audit_logger
        self.audit_config = audit_config

    def register(
        self, tool: Tool[Any], access_groups: Optional[List[str]] = None
    ) -> None:
        """Register a tool. Empty access_groups means accessible to all."""
        self.register_local_tool(tool, access_groups or [])

    def register_local_tool(self, tool: Tool[Any], access_groups: List[str]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")

        if access_groups:
            self._tools[tool.name] = _LocalToolWrapper(tool, access_groups)
        else:
            self._tools[tool.name] = tool

    async def get_tool(self, name: str) -> Optional[Tool[Any]]:
        return self._tools.get(name)

    async def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    async def get_schemas(self, user: Optional[User] = None) -> List[ToolSchema]:
        schemas: List[ToolSchema] = []
        for tool in self._tools.values():
            if user is None or await self._validate_tool_permissions(tool, user):
                schemas.append(tool.get_schema())
        return schemas

    async def _validate_tool_permissions(self, tool: Tool[Any], user: User) -> bool:
        tool_access_groups = tool.access_groups
        if not tool_access_groups:
            return True
        return bool(set(user.group_memberships) & set(tool_access_groups))

    async def transform_args(
        self,
        tool: Tool[T],
        args: T,
        user: User,
        context: ToolContext,
    ) -> Union[T, ToolRejection]:
        """Hook for per-user argument transformation (RLS etc.). Default: NoOp."""
        return args

    async def execute(self, tool_call: ToolCall, context: ToolContext) -> ToolResult:
        tool = await self.get_tool(tool_call.name)
        if not tool:
            msg = f"Tool '{tool_call.name}' not found"
            return ToolResult(success=False, result_for_llm=msg, error=msg)

        granted = await self._validate_tool_permissions(tool, context.user)
        if (
            self.audit_logger
            and self.audit_config
            and self.audit_config.enabled
            and self.audit_config.log_tool_access_checks
        ):
            await self.audit_logger.log_tool_access_check(
                user=context.user,
                tool_name=tool_call.name,
                access_granted=granted,
                required_groups=tool.access_groups,
                context=context,
                reason=None if granted else "insufficient group access",
            )

        if not granted:
            msg = f"Insufficient group access for tool '{tool_call.name}'"
            return ToolResult(success=False, result_for_llm=msg, error=msg)

        try:
            args_model = tool.get_args_schema()
            validated_args = args_model.model_validate(tool_call.arguments)
        except Exception as e:
            msg = f"Invalid arguments: {e}"
            return ToolResult(success=False, result_for_llm=msg, error=msg)

        transform_result = await self.transform_args(
            tool=tool,
            args=validated_args,
            user=context.user,
            context=context,
        )
        if isinstance(transform_result, ToolRejection):
            return ToolResult(
                success=False,
                result_for_llm=transform_result.reason,
                error=transform_result.reason,
            )

        if (
            self.audit_logger
            and self.audit_config
            and self.audit_config.enabled
            and self.audit_config.log_tool_invocations
        ):
            await self.audit_logger.log_tool_invocation(
                user=context.user, tool_call=tool_call, context=context
            )

        try:
            start = time.perf_counter()
            result = await tool.execute(context, transform_result)
            result.metadata["execution_time_ms"] = (time.perf_counter() - start) * 1000

            if (
                self.audit_logger
                and self.audit_config
                and self.audit_config.enabled
                and self.audit_config.log_tool_results
            ):
                await self.audit_logger.log_tool_result(
                    user=context.user,
                    tool_call=tool_call,
                    result=result,
                    context=context,
                )
            return result
        except Exception as e:
            msg = f"Execution failed: {e}"
            return ToolResult(success=False, result_for_llm=msg, error=msg)
