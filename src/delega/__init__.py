"""Delega Python SDK - Official client for the Delega API."""

from ._version import __version__
from .client import Delega
from .exceptions import (
    DelegaAPIError,
    DelegaAuthError,
    DelegaError,
    DelegaNotFoundError,
    DelegaRateLimitError,
)
from .models import Agent, Comment, Project, Task
from .webhooks import verify_webhook

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
    "verify_webhook",
]


def __getattr__(name: str) -> object:
    if name == "AsyncDelega":
        from .async_client import AsyncDelega

        return AsyncDelega
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
