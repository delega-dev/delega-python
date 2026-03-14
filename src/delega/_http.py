"""Low-level HTTP transport using urllib (stdlib only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from .exceptions import (
    DelegaAPIError,
    DelegaAuthError,
    DelegaError,
    DelegaNotFoundError,
    DelegaRateLimitError,
)

_DEFAULT_TIMEOUT = 30
_LOCAL_API_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _normalize_host(hostname: str) -> str:
    return hostname.strip("[]").lower()


def _is_local_host(hostname: str) -> bool:
    return _normalize_host(hostname) in _LOCAL_API_HOSTS


def normalize_base_url(raw_url: str) -> str:
    """Normalize a Delega base URL to include its API namespace."""
    parsed = urllib.parse.urlparse(raw_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise DelegaError(
            "Invalid Delega base_url. Use a full URL such as "
            "'https://api.delega.dev' or 'http://localhost:18890'."
        )

    if parsed.scheme != "https" and not _is_local_host(parsed.hostname or ""):
        raise DelegaError(
            "Delega base_url must use HTTPS unless it points to localhost."
        )

    path = parsed.path.rstrip("/")
    if not path:
        path = "/api" if _is_local_host(parsed.hostname or "") else "/v1"

    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, path, "", "", "")
    )


class HTTPClient:
    """Synchronous HTTP client using urllib."""

    def __init__(self, base_url: str, api_key: str, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self._base_url = normalize_base_url(base_url)
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "X-Agent-Key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        body: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Send an HTTP request and return the parsed JSON response.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            path: API path relative to the configured API namespace (e.g. ``/tasks``).
            params: Optional query parameters.
            body: Optional JSON request body.

        Returns:
            Parsed JSON response, or ``True`` for successful ``DELETE``
            requests with no body.

        Raises:
            DelegaAuthError: On 401/403 responses.
            DelegaNotFoundError: On 404 responses.
            DelegaRateLimitError: On 429 responses.
            DelegaAPIError: On other non-2xx responses.
        """
        url = self._base_url + path
        if params:
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                query = urllib.parse.urlencode(filtered, doseq=True)
                url = f"{url}?{query}"

        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                resp_body = resp.read().decode("utf-8")
                if not resp_body:
                    return True
                return json.loads(resp_body)
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            try:
                error_data = json.loads(error_body)
                message = error_data.get("error", error_data.get("message", error_body))
            except (json.JSONDecodeError, ValueError):
                message = error_body or exc.reason

            status = exc.code
            if status in (401, 403):
                raise DelegaAuthError(error_message=message, status_code=status) from exc
            if status == 404:
                raise DelegaNotFoundError(error_message=message) from exc
            if status == 429:
                raise DelegaRateLimitError(error_message=message) from exc
            raise DelegaAPIError(status_code=status, error_message=message) from exc

    def get(self, path: str, *, params: Optional[dict[str, Any]] = None) -> Any:
        """Send a GET request."""
        return self.request("GET", path, params=params)

    def post(self, path: str, *, body: Optional[dict[str, Any]] = None) -> Any:
        """Send a POST request."""
        return self.request("POST", path, body=body)

    def patch(self, path: str, *, body: Optional[dict[str, Any]] = None) -> Any:
        """Send a PATCH request."""
        return self.request("PATCH", path, body=body)

    def put(self, path: str, *, body: Optional[dict[str, Any]] = None) -> Any:
        """Send a PUT request."""
        return self.request("PUT", path, body=body)

    def delete(self, path: str) -> Any:
        """Send a DELETE request."""
        return self.request("DELETE", path)
