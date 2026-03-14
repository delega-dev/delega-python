"""Delega Python SDK - Official client for the Delega API."""

from .client import Delega
from .exceptions import (
    DelegaAPIError,
    DelegaAuthError,
    DelegaError,
    DelegaNotFoundError,
    DelegaRateLimitError,
)
from .models import Agent, Comment, Project, Task

__version__ = "0.1.1"

__all__ = [
    "Agent",
    "AsyncDelega",
    "Comment",
    "Delega",
    "DelegaAPIError",
    "DelegaAuthError",
    "DelegaError",
    "DelegaNotFoundError",
    "DelegaRateLimitError",
    "Project",
    "Task",
]


def __getattr__(name: str) -> object:
    if name == "AsyncDelega":
        from .async_client import AsyncDelega

        return AsyncDelega
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
