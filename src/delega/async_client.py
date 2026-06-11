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
from .models import (
    Agent,
    Comment,
    ContextEntry,
    ContextHistory,
    ContextSnapshot,
    DedupResult,
    DelegationChain,
    Project,
    Task,
    TaskLink,
    _normalize_merged_context,
)
from ._version import USER_AGENT

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
                "User-Agent": USER_AGENT,
            },
            timeout=timeout,
        )

    @property
    def path_prefix(self) -> str:
        """Return the API namespace path ("/v1" for hosted, "/api" for self-hosted)."""
        import urllib.parse
        return urllib.parse.urlparse(self._base_url).path or ""

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

    async def post(
        self,
        path: str,
        *,
        body: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        return await self.request("POST", path, params=params, body=body)

    async def patch(
        self,
        path: str,
        *,
        body: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        return await self.request("PATCH", path, params=params, body=body)

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
        claimed: Optional[bool] = None,
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
            # Contract: ?claimed=true|false (lowercase).
            "claimed": None if claimed is None else ("true" if claimed else "false"),
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
        project_id: Optional[str] = None,
        labels: Optional[list[str]] = None,
        due_date: Optional[str] = None,
        assigned_to_agent_id: Optional[str] = None,
    ) -> Task:
        """Create a delegated child task under a parent.

        The parent's ``status`` flips to ``"delegated"``. Use this — not
        ``assign()`` — for multi-agent handoffs so the parent/child
        accountability chain is recorded.
        """
        body: dict[str, Any] = {"content": content}
        if description is not None:
            body["description"] = description
        if priority is not None:
            body["priority"] = priority
        if project_id is not None:
            body["project_id"] = project_id
        if labels is not None:
            body["labels"] = labels
        if due_date is not None:
            body["due_date"] = due_date
        if assigned_to_agent_id is not None:
            body["assigned_to_agent_id"] = assigned_to_agent_id
        data = await self._http.post(f"/tasks/{parent_task_id}/delegate", body=body)
        return Task.from_dict(data)

    async def assign(self, task_id: str, agent_id: Optional[str]) -> Task:
        """Assign a task to an agent (or ``None`` to unassign)."""
        data = await self._http.put(
            f"/tasks/{task_id}", body={"assigned_to_agent_id": agent_id}
        )
        return Task.from_dict(data)

    async def chain(self, task_id: str) -> DelegationChain:
        """Get the full parent/child delegation chain for a task."""
        data = await self._http.get(f"/tasks/{task_id}/chain")
        return DelegationChain.from_dict(data)

    async def update_context(
        self,
        task_id: str,
        context: dict[str, Any],
        *,
        source: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> dict[str, Any]:
        """Deep-merge keys into a task's persistent context blob.

        Existing keys are preserved; supplied keys are added or overwritten.
        ``source`` attributes the write in the provenance ledger;
        ``expected_version`` is an optimistic-concurrency guard (409 on
        conflict).
        """
        params: dict[str, Any] = {}
        if source is not None:
            params["source"] = source
        if expected_version is not None:
            params["expected_version"] = expected_version
        data = await self._http.patch(
            f"/tasks/{task_id}/context", body=context, params=params or None
        )
        return _normalize_merged_context(data)

    async def get_context(
        self, task_id: str, *, include_provenance: bool = False
    ) -> ContextSnapshot:
        """Read a task's persistent context blob and its version."""
        params = {"include": "provenance"} if include_provenance else None
        data = await self._http.get(f"/tasks/{task_id}/context", params=params)
        return ContextSnapshot.from_dict(data)

    async def context_history(
        self,
        task_id: str,
        *,
        key: Optional[str] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> ContextHistory:
        """Read the append-only provenance ledger for a task's context."""
        params: dict[str, Any] = {"key": key, "limit": limit, "cursor": cursor}
        data = await self._http.get(f"/tasks/{task_id}/context/history", params=params)
        return ContextHistory.from_dict(data)

    async def supersede_context(self, task_id: str, key: str) -> ContextEntry:
        """Mark the live context entry for ``key`` as superseded (stale)."""
        data = await self._http.post(
            f"/tasks/{task_id}/context/supersede", body={"key": key}
        )
        entry = data.get("superseded") if isinstance(data, dict) else None
        return ContextEntry.from_dict(entry if isinstance(entry, dict) else data)

    async def set_state(
        self, task_id: str, state: str, *, detail: Optional[str] = None
    ) -> Task:
        """Report a session state (``working``/``waiting_input``/``errored``).

        Requires holding an active claim on the task (409 otherwise).
        """
        body: dict[str, Any] = {"state": state}
        if detail is not None:
            body["detail"] = detail
        data = await self._http.post(f"/tasks/{task_id}/state", body=body)
        return Task.from_dict(data)

    async def list_links(self, task_id: str) -> list[TaskLink]:
        """List the repo/URL links attached to a task."""
        data = await self._http.get(f"/tasks/{task_id}/links")
        return [TaskLink.from_dict(l) for l in data]

    async def add_link(
        self,
        task_id: str,
        kind: str,
        ref: str,
        *,
        repo: Optional[str] = None,
        url: Optional[str] = None,
    ) -> TaskLink:
        """Attach a branch, commit, PR, or URL link to a task."""
        body: dict[str, Any] = {"kind": kind, "ref": ref}
        if repo is not None:
            body["repo"] = repo
        if url is not None:
            body["url"] = url
        data = await self._http.post(f"/tasks/{task_id}/links", body=body)
        return TaskLink.from_dict(data)

    async def delete_link(self, task_id: str, link_id: str) -> bool:
        """Remove a link from a task."""
        await self._http.delete(f"/tasks/{task_id}/links/{link_id}")
        return True

    async def find_duplicates(
        self, content: str, *, threshold: Optional[float] = None
    ) -> DedupResult:
        """Check whether content is similar to existing open tasks."""
        body: dict[str, Any] = {"content": content}
        if threshold is not None:
            body["threshold"] = threshold
        data = await self._http.post("/tasks/dedup", body=body)
        return DedupResult.from_dict(data)

    async def claim(
        self,
        *,
        task_id: Optional[str] = None,
        project_id: Optional[str] = None,
        labels: Optional[list[str]] = None,
        lease_seconds: Optional[int] = None,
    ) -> Optional[Task]:
        """Atomically claim a task: the next from the queue, or a specific one.

        Tasks are claimed in priority order (priority ASC, then
        created_at ASC). The claim holds a lease; call ``heartbeat()``
        to extend it while working, and ``release()`` to give the task
        back to the queue. Claiming never modifies
        ``assigned_to_agent_id``. Pass ``task_id`` to claim a specific
        task (409 if it is not claimable).

        Returns:
            The claimed :class:`Task`, or ``None`` if no claimable task
            is available (queue mode only).
        """
        body: dict[str, Any] = {}
        if lease_seconds is not None:
            body["lease_seconds"] = lease_seconds
        if task_id is not None:
            data = await self._http.post(f"/tasks/{task_id}/claim", body=body)
        else:
            if project_id is not None:
                body["project_id"] = project_id
            if labels is not None:
                body["labels"] = labels
            data = await self._http.post("/tasks/claim", body=body)
        task = data.get("task") if isinstance(data, dict) else None
        if task is None:
            return None
        return Task.from_dict(task)

    async def heartbeat(
        self, task_id: str, *, lease_seconds: Optional[int] = None
    ) -> Task:
        """Extend the lease on a task this agent has claimed.

        Raises a 409 :class:`DelegaAPIError` if the caller does not
        hold an active claim on the task.
        """
        body: dict[str, Any] = {}
        if lease_seconds is not None:
            body["lease_seconds"] = lease_seconds
        data = await self._http.post(f"/tasks/{task_id}/heartbeat", body=body)
        return Task.from_dict(data)

    async def release(self, task_id: str) -> Task:
        """Release a claimed task back to the queue (status ``"open"``).

        Only the claim holder or an admin may release.
        """
        data = await self._http.post(f"/tasks/{task_id}/release")
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
        role: Optional[str] = None,
    ) -> Agent:
        """Create a new agent. Returns api_key in the response.

        ``role`` is an optional preset: ``"worker"`` (default),
        ``"coordinator"``, or ``"admin"``.
        """
        body: dict[str, Any] = {"name": name}
        if display_name is not None:
            body["display_name"] = display_name
        if description is not None:
            body["description"] = description
        if role is not None:
            body["role"] = role
        data = await self._http.post("/agents", body=body)
        return Agent.from_dict(data)

    async def update(self, agent_id: str, **fields: Any) -> Agent:
        """Update an agent."""
        data = await self._http.put(f"/agents/{agent_id}", body=fields)
        return Agent.from_dict(data)

    async def set_role(self, agent_id: str, role: str) -> Agent:
        """Set an agent's role (admin key required): worker, coordinator, or admin."""
        data = await self._http.put(f"/agents/{agent_id}", body={"role": role})
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
            the ``DELEGA_API_KEY`` environment variable, falling back to
            ``DELEGA_AGENT_KEY`` for cross-client consistency with the
            ``@delega-dev/mcp`` package.
        base_url: Base URL of the Delega API. Defaults to
            ``https://api.delega.dev`` (normalized to ``/v1``). To target
            a custom endpoint, use ``http://localhost:18890`` or an
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
        resolved_key = (
            api_key
            or os.environ.get("DELEGA_API_KEY")
            or os.environ.get("DELEGA_AGENT_KEY")
        )
        if not resolved_key:
            raise DelegaError(
                "No API key provided. Pass api_key= or set DELEGA_API_KEY "
                "(or DELEGA_AGENT_KEY) in the environment."
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
        """Get quota and rate-limit information for the current plan.

        Hosted API only (``api.delega.dev``). Custom ``/api`` endpoints
        will raise :class:`DelegaError` before making a request.
        """
        if self._http.path_prefix != "/v1":
            raise DelegaError(
                "usage() is only available on the hosted Delega API "
                "(api.delega.dev). Self-hosted deployments do not expose "
                "a usage endpoint."
            )
        return await self._http.get("/usage")  # type: ignore[no-any-return]

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> AsyncDelega:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()
