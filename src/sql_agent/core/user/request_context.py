"""Request context for user resolution."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class RequestContext(BaseModel):
    """Context from a web/CLI request for user resolution."""

    cookies: Dict[str, str] = Field(default_factory=dict)
    headers: Dict[str, str] = Field(default_factory=dict)
    remote_addr: Optional[str] = Field(default=None)
    query_params: Dict[str, str] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def get_cookie(self, name: str, default: Optional[str] = None) -> Optional[str]:
        return self.cookies.get(name, default)

    def get_header(self, name: str, default: Optional[str] = None) -> Optional[str]:
        name_lower = name.lower()
        for key, value in self.headers.items():
            if key.lower() == name_lower:
                return value
        return default
