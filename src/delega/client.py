"""Synchronous Delega API client."""

from __future__ import annotations

import os
from typing import Any, Optional

from ._http import HTTPClient
from .exceptions import DelegaError
from .models import (
    Agent,
    Comment,
    DedupResult,
    DelegationChain,
    Project,
    Task,
)

_DEFAULT_BASE_URL = "https://api.delega.dev"


class _TasksNamespace:
    """Namespace for task-related API methods."""

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    def list(
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
        """List tasks with optional filters.

        Args:
            priority: Filter by priority level.
            search: Search query string.
            label: Filter by a single label.
            labels: Filter by multiple labels.
            due: Filter by exact due date.
            due_after: Filter tasks due after this date.
            due_before: Filter tasks due before this date.
            completed: Filter by completion status.
        """
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
        data = self._http.get("/tasks", params=params)
        return [Task.from_dict(t) for t in data]

    def create(
        self,
        content: str,
        *,
        description: Optional[str] = None,
        priority: int = 2,
        labels: Optional[list[str]] = None,
        due_date: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Task:
        """Create a new task.

        Args:
            content: The task content/title.
            description: Optional longer description.
            priority: Priority level (default 2).
            labels: Optional list of labels.
            due_date: Optional due date string.
            project_id: Optional project to assign the task to.
        """
        body: dict[str, Any] = {"content": content, "priority": priority}
        if description is not None:
            body["description"] = description
        if labels is not None:
            body["labels"] = labels
        if due_date is not None:
            body["due_date"] = due_date
        if project_id is not None:
            body["project_id"] = project_id
        data = self._http.post("/tasks", body=body)
        return Task.from_dict(data)

    def get(self, task_id: str) -> Task:
        """Get a task by ID.

        Args:
            task_id: The task identifier.
        """
        data = self._http.get(f"/tasks/{task_id}")
        return Task.from_dict(data)

    def update(self, task_id: str, **fields: Any) -> Task:
        """Update a task.

        Args:
            task_id: The task identifier.
            **fields: Fields to update (content, description, priority, etc.).
        """
        data = self._http.put(f"/tasks/{task_id}", body=fields)
        return Task.from_dict(data)

    def delete(self, task_id: str) -> bool:
        """Delete a task.

        Args:
            task_id: The task identifier.

        Returns:
            ``True`` if the task was deleted successfully.
        """
        self._http.delete(f"/tasks/{task_id}")
        return True

    def complete(self, task_id: str) -> Task:
        """Mark a task as completed.

        Args:
            task_id: The task identifier.
        """
        data = self._http.post(f"/tasks/{task_id}/complete")
        return Task.from_dict(data)

    def uncomplete(self, task_id: str) -> Task:
        """Mark a task as not completed.

        Args:
            task_id: The task identifier.
        """
        data = self._http.post(f"/tasks/{task_id}/uncomplete")
        return Task.from_dict(data)

    def search(self, query: str) -> list[Task]:
        """Search tasks by query string.

        This is a shortcut for ``list(search=query)``.

        Args:
            query: The search query.
        """
        return self.list(search=query)

    def delegate(
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
        accountability chain is recorded (inspectable via ``chain()``).

        Args:
            parent_task_id: The parent task identifier.
            content: The child task content/title.
            description: Optional longer description.
            priority: Optional priority level (1-4).
            project_id: Optional project to attach the child to.
            labels: Optional labels for the child.
            due_date: Optional due date (YYYY-MM-DD).
            assigned_to_agent_id: Optional agent to assign the child to.
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
        data = self._http.post(f"/tasks/{parent_task_id}/delegate", body=body)
        return Task.from_dict(data)

    def assign(self, task_id: str, agent_id: Optional[str]) -> Task:
        """Assign a task to an agent (or ``None`` to unassign).

        For multi-agent handoffs where you want the parent/child chain
        recorded, use ``delegate()`` instead — ``assign()`` only updates
        the assignee on an existing task.

        Args:
            task_id: The task identifier.
            agent_id: The agent identifier, or ``None`` to unassign.
        """
        data = self._http.put(
            f"/tasks/{task_id}", body={"assigned_to_agent_id": agent_id}
        )
        return Task.from_dict(data)

    def chain(self, task_id: str) -> DelegationChain:
        """Get the full parent/child delegation chain for a task.

        Normalizes hosted (``{root_id}``) vs self-hosted (``{root: Task}``)
        response shapes so ``DelegationChain.root_id`` is always populated.

        Args:
            task_id: Any task identifier in the chain.
        """
        data = self._http.get(f"/tasks/{task_id}/chain")
        return DelegationChain.from_dict(data)

    def update_context(
        self, task_id: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        """Deep-merge keys into a task's persistent context blob.

        Existing keys are preserved; supplied keys are added or overwritten.
        Use this to pass shared state between delegated agents instead of
        re-describing context in task descriptions.

        Args:
            task_id: The task identifier.
            context: Keys to merge into the existing context.

        Returns:
            The merged context dict.
        """
        # Hosted returns the bare merged context dict; self-hosted returns
        # the full Task with a ``context`` field. Normalize to always
        # return the merged context.
        data = self._http.patch(f"/tasks/{task_id}/context", body=context)
        if isinstance(data, dict) and "content" in data and "id" in data:
            # Looks like a full Task.
            raw_ctx = data.get("context") or {}
            if isinstance(raw_ctx, str):
                import json as _json
                try:
                    raw_ctx = _json.loads(raw_ctx) if raw_ctx.strip() else {}
                except Exception:
                    raw_ctx = {}
            return raw_ctx if isinstance(raw_ctx, dict) else {}
        return data if isinstance(data, dict) else {}

    def find_duplicates(
        self, content: str, *, threshold: Optional[float] = None
    ) -> DedupResult:
        """Check whether content is similar to existing open tasks.

        Call before ``create()`` to avoid redundant work. Uses Jaccard
        similarity against open tasks.

        Args:
            content: The proposed task content to check.
            threshold: Similarity threshold 0-1 (default 0.6 server-side).
        """
        body: dict[str, Any] = {"content": content}
        if threshold is not None:
            body["threshold"] = threshold
        data = self._http.post("/tasks/dedup", body=body)
        return DedupResult.from_dict(data)

    def add_comment(self, task_id: str, content: str) -> Comment:
        """Add a comment to a task.

        Args:
            task_id: The task identifier.
            content: The comment text.
        """
        data = self._http.post(f"/tasks/{task_id}/comments", body={"content": content})
        return Comment.from_dict(data)

    def list_comments(self, task_id: str) -> list[Comment]:
        """List all comments on a task.

        Args:
            task_id: The task identifier.
        """
        data = self._http.get(f"/tasks/{task_id}/comments")
        return [Comment.from_dict(c) for c in data]


class _AgentsNamespace:
    """Namespace for agent-related API methods."""

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    def list(self) -> list[Agent]:
        """List all agents."""
        data = self._http.get("/agents")
        return [Agent.from_dict(a) for a in data]

    def create(
        self,
        name: str,
        *,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Agent:
        """Create a new agent.

        The response includes the agent's ``api_key``, which is only
        returned at creation time.

        Args:
            name: Unique agent name.
            display_name: Optional human-friendly display name.
            description: Optional description.
        """
        body: dict[str, Any] = {"name": name}
        if display_name is not None:
            body["display_name"] = display_name
        if description is not None:
            body["description"] = description
        data = self._http.post("/agents", body=body)
        return Agent.from_dict(data)

    def update(self, agent_id: str, **fields: Any) -> Agent:
        """Update an agent.

        Args:
            agent_id: The agent identifier.
            **fields: Fields to update (name, display_name, description).
        """
        data = self._http.patch(f"/agents/{agent_id}", body=fields)
        return Agent.from_dict(data)

    def delete(self, agent_id: str) -> bool:
        """Delete an agent.

        Args:
            agent_id: The agent identifier.

        Returns:
            ``True`` if the agent was deleted successfully.
        """
        self._http.delete(f"/agents/{agent_id}")
        return True

    def rotate_key(self, agent_id: str) -> dict[str, Any]:
        """Rotate an agent's API key.

        Args:
            agent_id: The agent identifier.

        Returns:
            Dictionary containing the new ``api_key``.
        """
        data = self._http.post(f"/agents/{agent_id}/rotate-key")
        return data  # type: ignore[no-any-return]


class _ProjectsNamespace:
    """Namespace for project-related API methods."""

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    def list(self) -> list[Project]:
        """List all projects."""
        data = self._http.get("/projects")
        return [Project.from_dict(p) for p in data]

    def create(
        self,
        name: str,
        *,
        emoji: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Project:
        """Create a new project.

        Args:
            name: Project name.
            emoji: Optional emoji icon.
            color: Optional color hex code.
        """
        body: dict[str, Any] = {"name": name}
        if emoji is not None:
            body["emoji"] = emoji
        if color is not None:
            body["color"] = color
        data = self._http.post("/projects", body=body)
        return Project.from_dict(data)


class _WebhooksNamespace:
    """Namespace for webhook-related API methods."""

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    def list(self) -> list[Any]:
        """List all webhooks."""
        return self._http.get("/webhooks")  # type: ignore[no-any-return]

    def create(
        self,
        url: str,
        *,
        events: Optional[list[str]] = None,
        secret: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new webhook.

        Args:
            url: The webhook endpoint URL.
            events: Optional list of event types to subscribe to.
            secret: Optional signing secret for verifying payloads.
        """
        body: dict[str, Any] = {"url": url}
        if events is not None:
            body["events"] = events
        if secret is not None:
            body["secret"] = secret
        return self._http.post("/webhooks", body=body)  # type: ignore[no-any-return]

    def delete(self, webhook_id: str) -> bool:
        """Delete a webhook.

        Args:
            webhook_id: The webhook identifier.
        """
        self._http.delete(f"/webhooks/{webhook_id}")
        return True


class Delega:
    """Synchronous client for the Delega API.

    Example::

        from delega import Delega

        client = Delega(api_key="dlg_...")
        tasks = client.tasks.list()

    Args:
        api_key: API key for authentication. If not provided, reads from
            the ``DELEGA_API_KEY`` environment variable, falling back to
            ``DELEGA_AGENT_KEY`` for cross-client consistency with the
            ``@delega-dev/mcp`` package.
        base_url: Base URL of the Delega API. Defaults to
            ``https://api.delega.dev`` (normalized to ``/v1``). For
            self-hosted deployments, use ``http://localhost:18890`` or an
            explicit ``.../api`` base URL.
        timeout: Request timeout in seconds. Defaults to 30.

    Raises:
        DelegaError: If no API key is provided or found in the environment.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int = 30,
    ) -> None:
        # Accept both env vars so agents configuring the MCP (primary:
        # DELEGA_AGENT_KEY) and this SDK (primary: DELEGA_API_KEY) in one
        # shell don't need to set both. DELEGA_API_KEY wins when both set.
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
        self._http = HTTPClient(base_url=base_url, api_key=resolved_key, timeout=timeout)
        self.tasks = _TasksNamespace(self._http)
        self.agents = _AgentsNamespace(self._http)
        self.projects = _ProjectsNamespace(self._http)
        self.webhooks = _WebhooksNamespace(self._http)

    def me(self) -> dict[str, Any]:
        """Get information about the authenticated agent.

        Returns:
            Dictionary with agent details.
        """
        return self._http.get("/agent/me")  # type: ignore[no-any-return]

    def usage(self) -> dict[str, Any]:
        """Get quota and rate-limit information for the current plan.

        Hosted API only (``api.delega.dev``). Self-hosted deployments
        will raise :class:`DelegaError` before making a request.

        Returns:
            Dict with ``plan``, ``task_count_month``, ``task_limit``,
            ``reset_date``, ``agent_count``, ``agent_limit``,
            ``webhook_count``, ``webhook_limit``, ``project_count``,
            ``project_limit``, ``rate_limit_rpm``, ``max_content_chars``.
        """
        if self._http.path_prefix != "/v1":
            raise DelegaError(
                "usage() is only available on the hosted Delega API "
                "(api.delega.dev). Self-hosted deployments do not expose "
                "a usage endpoint."
            )
        return self._http.get("/usage")  # type: ignore[no-any-return]
