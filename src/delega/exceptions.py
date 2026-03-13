"""Exceptions for the Delega SDK."""

from __future__ import annotations


class DelegaError(Exception):
    """Base exception for all Delega SDK errors."""


class DelegaAPIError(DelegaError):
    """Raised when the Delega API returns an error response."""

    def __init__(self, status_code: int, error_message: str) -> None:
        self.status_code = status_code
        self.error_message = error_message
        super().__init__(f"API error {status_code}: {error_message}")


class DelegaAuthError(DelegaAPIError):
    """Raised when the API returns a 401 or 403 status code."""

    def __init__(self, error_message: str, status_code: int = 401) -> None:
        super().__init__(status_code=status_code, error_message=error_message)


class DelegaNotFoundError(DelegaAPIError):
    """Raised when the API returns a 404 status code."""

    def __init__(self, error_message: str) -> None:
        super().__init__(status_code=404, error_message=error_message)


class DelegaRateLimitError(DelegaAPIError):
    """Raised when the API returns a 429 status code."""

    def __init__(self, error_message: str) -> None:
        super().__init__(status_code=429, error_message=error_message)
