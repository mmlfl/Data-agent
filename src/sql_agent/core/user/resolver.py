"""User resolver interface."""

from abc import ABC, abstractmethod

from sql_agent.core.user.models import User
from sql_agent.core.user.request_context import RequestContext


class UserResolver(ABC):
    """Resolves request context to an authenticated User."""

    @abstractmethod
    async def resolve_user(self, request_context: RequestContext) -> User:
        """Resolve user from request context."""


class FixedUserResolver(UserResolver):
    """Placeholder resolver that always returns the same user (no real auth)."""

    def __init__(
        self,
        user_id: str = "local",
        username: str = "local",
        group_memberships: list[str] | None = None,
    ) -> None:
        self._user = User(
            id=user_id,
            username=username,
            group_memberships=group_memberships or ["user"],
        )

    async def resolve_user(self, request_context: RequestContext) -> User:
        return self._user
