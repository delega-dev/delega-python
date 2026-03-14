"""Asynchronous Delega API client using httpx."""

from __future__ import annotations

import os
from typing import Any, Optional

from ._http import normalize_base_url
from .exceptions import (
    DelegaAPIError,
    DelegaAuthError,
    DelegaError,
    DelegaNotFoundError,
    DelegaRateLimitError,
)
from .models import Agent, Comment, Project, Task

_DEFAULT_BASE_URL = "https://api.delega.dev"


def _require_httpx() -> Any:
    try:
        import httpx  # noqa: F811

        return httpx
    except ImportError:
        raise ImportError(
            "httpx is required for the async client. "
            "Install it with: pip install 'delega[async]'"
        ) from None


class _AsyncHTTPClient:
    """Async HTTP transport using httpx."""

    def __init__(self, base_url: str, api_key: str, timeout: int = 30) -> None:
        httpx = _require_httpx()
        self._base_url = normalize_base_url(base_url)
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "X-Agent-Key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=timeout,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        body: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Send an async HTTP request and return parsed JSON."""
        filtered_params = None
        if params:
            filtered_params = {k: v for k, v in params.items() if v is not None}
            if not filtered_params:
                filtered_params = None

        resp = await self._client.request(
            method,
            path,
            params=filtered_params,
            json=body,
        )

        if resp.status_code >= 400:
            try:
                error_data = resp.json()
                message = error_data.get("error", error_data.get("message", resp.text))
            except Exception:
                message = resp.text or resp.reason_phrase

            status = resp.status_code
            if status in (401, 403):
                raise DelegaAuthError(error_message=message, status_code=status)
            if status == 404:
                raise DelegaNotFoundError(error_message=message)
            if status == 429:
                raise DelegaRateLimitError(error_message=message)
            raise DelegaAPIError(status_code=status, error_message=message)

        if not resp.text:
            return True
        return resp.json()

    async def get(self, path: str, *, params: Optional[dict[str, Any]] = None) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, *, body: Optional[dict[str, Any]] = None) -> Any:
        return await self.request("POST", path, body=body)

    async def patch(self, path: str, *, body: Optional[dict[str, Any]] = None) -> Any:
        return await self.request("PATCH", path, body=body)

    async def put(self, path: str, *, body: Optional[dict[str, Any]] = None) -> Any:
        return await self.request("PUT", path, body=body)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)

    async def aclose(self) -> None:
        await self._client.aclose()


class _AsyncTasksNamespace:
    """Async namespace for task-related API methods."""

    def __init__(self, http: _AsyncHTTPClient) -> None:
        self._http = http

    async def list(
        self,
        *,
        priority: Optional[int] = None,
        search: Optional[str] = None,
        label: Optional[str] = None,
        labels: Optional[list[str]] = None,
        due: Optional[str] = None,
        due_after: Optional[str] = None,
        due_before: Optional[str] = None,
        completed: Optional[bool] = None,
    ) -> list[Task]:
        """List tasks with optional filters."""
        params: dict[str, Any] = {
            "priority": priority,
            "search": search,
            "label": label,
            "labels": labels,
            "due": due,
            "due_after": due_after,
            "due_before": due_before,
            "completed": completed,
        }
        data = await self._http.get("/tasks", params=params)
        return [Task.from_dict(t) for t in data]

    async def create(
        self,
        content: str,
        *,
        description: Optional[str] = None,
        priority: int = 2,
        labels: Optional[list[str]] = None,
        due_date: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Task:
        """Create a new task."""
        body: dict[str, Any] = {"content": content, "priority": priority}
        if description is not None:
            body["description"] = description
        if labels is not None:
            body["labels"] = labels
        if due_date is not None:
            body["due_date"] = due_date
        if project_id is not None:
            body["project_id"] = project_id
        data = await self._http.post("/tasks", body=body)
        return Task.from_dict(data)

    async def get(self, task_id: str) -> Task:
        """Get a task by ID."""
        data = await self._http.get(f"/tasks/{task_id}")
        return Task.from_dict(data)

    async def update(self, task_id: str, **fields: Any) -> Task:
        """Update a task."""
        data = await self._http.patch(f"/tasks/{task_id}", body=fields)
        return Task.from_dict(data)

    async def delete(self, task_id: str) -> bool:
        """Delete a task."""
        await self._http.delete(f"/tasks/{task_id}")
        return True

    async def complete(self, task_id: str) -> Task:
        """Mark a task as completed."""
        data = await self._http.post(f"/tasks/{task_id}/complete")
        return Task.from_dict(data)

    async def uncomplete(self, task_id: str) -> Task:
        """Mark a task as not completed."""
        data = await self._http.post(f"/tasks/{task_id}/uncomplete")
        return Task.from_dict(data)

    async def search(self, query: str) -> list[Task]:
        """Search tasks by query string."""
        return await self.list(search=query)

    async def delegate(
        self,
        parent_task_id: str,
        content: str,
        *,
        description: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> Task:
        """Create a delegated sub-task under a parent task."""
        body: dict[str, Any] = {"content": content}
        if description is not None:
            body["description"] = description
        if priority is not None:
            body["priority"] = priority
        data = await self._http.post(f"/tasks/{parent_task_id}/delegate", body=body)
        return Task.from_dict(data)

    async def add_comment(self, task_id: str, content: str) -> Comment:
        """Add a comment to a task."""
        data = await self._http.post(f"/tasks/{task_id}/comments", body={"content": content})
        return Comment.from_dict(data)

    async def list_comments(self, task_id: str) -> list[Comment]:
        """List all comments on a task."""
        data = await self._http.get(f"/tasks/{task_id}/comments")
        return [Comment.from_dict(c) for c in data]


class _AsyncAgentsNamespace:
    """Async namespace for agent-related API methods."""

    def __init__(self, http: _AsyncHTTPClient) -> None:
        self._http = http

    async def list(self) -> list[Agent]:
        """List all agents."""
        data = await self._http.get("/agents")
        return [Agent.from_dict(a) for a in data]

    async def create(
        self,
        name: str,
        *,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Agent:
        """Create a new agent. Returns api_key in the response."""
        body: dict[str, Any] = {"name": name}
        if display_name is not None:
            body["display_name"] = display_name
        if description is not None:
            body["description"] = description
        data = await self._http.post("/agents", body=body)
        return Agent.from_dict(data)

    async def update(self, agent_id: str, **fields: Any) -> Agent:
        """Update an agent."""
        data = await self._http.patch(f"/agents/{agent_id}", body=fields)
        return Agent.from_dict(data)

    async def delete(self, agent_id: str) -> bool:
        """Delete an agent."""
        await self._http.delete(f"/agents/{agent_id}")
        return True

    async def rotate_key(self, agent_id: str) -> dict[str, Any]:
        """Rotate an agent's API key."""
        data = await self._http.post(f"/agents/{agent_id}/rotate-key")
        return data  # type: ignore[no-any-return]


class _AsyncProjectsNamespace:
    """Async namespace for project-related API methods."""

    def __init__(self, http: _AsyncHTTPClient) -> None:
        self._http = http

    async def list(self) -> list[Project]:
        """List all projects."""
        data = await self._http.get("/projects")
        return [Project.from_dict(p) for p in data]

    async def create(
        self,
        name: str,
        *,
        emoji: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Project:
        """Create a new project."""
        body: dict[str, Any] = {"name": name}
        if emoji is not None:
            body["emoji"] = emoji
        if color is not None:
            body["color"] = color
        data = await self._http.post("/projects", body=body)
        return Project.from_dict(data)


class _AsyncWebhooksNamespace:
    """Async namespace for webhook-related API methods."""

    def __init__(self, http: _AsyncHTTPClient) -> None:
        self._http = http

    async def list(self) -> list[Any]:
        """List all webhooks."""
        return await self._http.get("/webhooks")  # type: ignore[no-any-return]

    async def create(
        self,
        url: str,
        *,
        events: Optional[list[str]] = None,
        secret: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new webhook."""
        body: dict[str, Any] = {"url": url}
        if events is not None:
            body["events"] = events
        if secret is not None:
            body["secret"] = secret
        return await self._http.post("/webhooks", body=body)  # type: ignore[no-any-return]


class AsyncDelega:
    """Asynchronous client for the Delega API.

    Requires ``httpx``. Install with: ``pip install 'delega[async]'``

    Example::

        from delega import AsyncDelega

        async with AsyncDelega(api_key="dlg_...") as client:
            tasks = await client.tasks.list()

    Args:
        api_key: API key for authentication. If not provided, reads from
            the ``DELEGA_API_KEY`` environment variable.
        base_url: Base URL of the Delega API. Defaults to
            ``https://api.delega.dev`` (normalized to ``/v1``). For
            self-hosted deployments, use ``http://localhost:18890`` or an
            explicit ``.../api`` base URL.
        timeout: Request timeout in seconds. Defaults to 30.

    Raises:
        DelegaError: If no API key is provided or found in the environment.
        ImportError: If httpx is not installed.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int = 30,
    ) -> None:
        resolved_key = api_key or os.environ.get("DELEGA_API_KEY")
        if not resolved_key:
            raise DelegaError(
                "No API key provided. Pass api_key= or set the DELEGA_API_KEY environment variable."
            )
        self._http = _AsyncHTTPClient(base_url=base_url, api_key=resolved_key, timeout=timeout)
        self.tasks = _AsyncTasksNamespace(self._http)
        self.agents = _AsyncAgentsNamespace(self._http)
        self.projects = _AsyncProjectsNamespace(self._http)
        self.webhooks = _AsyncWebhooksNamespace(self._http)

    async def me(self) -> dict[str, Any]:
        """Get information about the authenticated agent."""
        return await self._http.get("/agent/me")  # type: ignore[no-any-return]

    async def usage(self) -> dict[str, Any]:
        """Get API usage information."""
        return await self._http.get("/usage")  # type: ignore[no-any-return]

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> AsyncDelega:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()
