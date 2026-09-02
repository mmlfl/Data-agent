"""Tool abstract base class."""

from abc import ABC, abstractmethod
from typing import Any, Generic, List, Type, TypeVar, cast

from sql_agent.core.tool.models import ToolContext, ToolResult, ToolSchema

T = TypeVar("T")


class Tool(ABC, Generic[T]):
    """Abstract base class for tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this tool."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what this tool does."""

    @property
    def access_groups(self) -> List[str]:
        """Groups permitted to access this tool. Empty = all users."""
        return []

    @abstractmethod
    def get_args_schema(self) -> Type[T]:
        """Return the Pydantic model for arguments."""

    @abstractmethod
    async def execute(self, context: ToolContext, args: T) -> ToolResult:
        """Execute the tool with validated arguments."""

    def get_schema(self) -> ToolSchema:
        """Generate tool schema for LLM (JSON Schema from Pydantic)."""
        args_model = self.get_args_schema()
        schema = (
            cast(Any, args_model).model_json_schema()
            if hasattr(args_model, "model_json_schema")
            else {}
        )
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=schema,
            access_groups=self.access_groups,
        )
