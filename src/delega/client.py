"""Synchronous Delega API client."""

from __future__ import annotations

import os
from typing import Any, Optional

from ._http import (
    HTTPClient,
    cloudflare_access_headers,
    encode_path_segment as _seg,
)
from .exceptions import DelegaError
from .models import (
    Agent,
    Comment,
    ContextEntry,
    ContextHistory,
    ContextSnapshot,
    DedupResult,
    DelegationChain,
    Project,
    Recurrence,
    Task,
    TaskLink,
    _normalize_merged_context,
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
        claimed: Optional[bool] = None,
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
            claimed: Filter by claim status (``True`` for claimed tasks,
                ``False`` for unclaimed tasks).
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
            "claimed": claimed,
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
        data = self._http.get(f"/tasks/{_seg(task_id)}")
        return Task.from_dict(data)

    def update(self, task_id: str, **fields: Any) -> Task:
        """Update a task.

        Args:
            task_id: The task identifier.
            **fields: Fields to update (content, description, priority, etc.).
        """
        data = self._http.put(f"/tasks/{_seg(task_id)}", body=fields)
        return Task.from_dict(data)

    def delete(self, task_id: str) -> bool:
        """Delete a task.

        Args:
            task_id: The task identifier.

        Returns:
            ``True`` if the task was deleted successfully.
        """
        self._http.delete(f"/tasks/{_seg(task_id)}")
        return True

    def complete(self, task_id: str) -> Task:
        """Mark a task as completed.

        Args:
            task_id: The task identifier.
        """
        data = self._http.post(f"/tasks/{_seg(task_id)}/complete")
        return Task.from_dict(data)

    def uncomplete(self, task_id: str) -> Task:
        """Mark a task as not completed.

        Args:
            task_id: The task identifier.
        """
        data = self._http.post(f"/tasks/{_seg(task_id)}/uncomplete")
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
        data = self._http.post(f"/tasks/{_seg(parent_task_id)}/delegate", body=body)
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
            f"/tasks/{_seg(task_id)}", body={"assigned_to_agent_id": agent_id}
        )
        return Task.from_dict(data)

    def chain(self, task_id: str) -> DelegationChain:
        """Get the full parent/child delegation chain for a task.

        Normalizes hosted (``{root_id}``) vs self-hosted (``{root: Task}``)
        response shapes so ``DelegationChain.root_id`` is always populated.

        Args:
            task_id: Any task identifier in the chain.
        """
        data = self._http.get(f"/tasks/{_seg(task_id)}/chain")
        return DelegationChain.from_dict(data)

    def update_context(
        self,
        task_id: str,
        context: dict[str, Any],
        *,
        source: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> dict[str, Any]:
        """Deep-merge keys into a task's persistent context blob.

        Existing keys are preserved; supplied keys are added or overwritten.
        Use this to pass shared state between delegated agents instead of
        re-describing context in task descriptions.

        Args:
            task_id: The task identifier.
            context: Keys to merge into the existing context.
            source: Provenance attribution for this write — one of
                ``"human_stated"``, ``"agent_inferred"``,
                ``"agent_observed"``, ``"imported"`` (server default
                ``agent_inferred``; ``human_stated``/``imported`` require
                an admin key).
            expected_version: Optimistic concurrency guard — the context
                version from ``get_context()``. If the context changed
                since that read, the write fails with a 409
                :class:`DelegaAPIError` whose message includes the
                current version.

        Returns:
            The merged context dict.
        """
        params: dict[str, Any] = {}
        if source is not None:
            params["source"] = source
        if expected_version is not None:
            params["expected_version"] = expected_version
        data = self._http.patch(
            f"/tasks/{_seg(task_id)}/context", body=context, params=params or None
        )
        return _normalize_merged_context(data)

    def get_context(
        self, task_id: str, *, include_provenance: bool = False
    ) -> ContextSnapshot:
        """Read a task's persistent context blob and its version.

        Args:
            task_id: The task identifier.
            include_provenance: When ``True``, also return per-key
                author/source/version provenance for the live entries.
        """
        params = {"include": "provenance"} if include_provenance else None
        data = self._http.get(f"/tasks/{_seg(task_id)}/context", params=params)
        return ContextSnapshot.from_dict(data)

    def context_history(
        self,
        task_id: str,
        *,
        key: Optional[str] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> ContextHistory:
        """Read the append-only provenance ledger for a task's context.

        Args:
            task_id: The task identifier.
            key: Narrow history to one context key; omit for the newest
                entries across all keys.
            limit: Page size (server default 100, max 100).
            cursor: Opaque cursor from a previous page's ``next_cursor``.
        """
        params: dict[str, Any] = {"key": key, "limit": limit, "cursor": cursor}
        data = self._http.get(f"/tasks/{_seg(task_id)}/context/history", params=params)
        return ContextHistory.from_dict(data)

    def supersede_context(self, task_id: str, key: str) -> ContextEntry:
        """Mark the live context entry for ``key`` as superseded (stale).

        The context value itself is not changed — this only records in the
        provenance ledger that the entry should no longer be trusted.

        Args:
            task_id: The task identifier.
            key: The context key to supersede.

        Returns:
            The superseded :class:`ContextEntry`.
        """
        data = self._http.post(
            f"/tasks/{_seg(task_id)}/context/supersede", body={"key": key}
        )
        entry = data.get("superseded") if isinstance(data, dict) else None
        return ContextEntry.from_dict(entry if isinstance(entry, dict) else data)

    def set_state(
        self, task_id: str, state: str, *, detail: Optional[str] = None
    ) -> Task:
        """Report a session state on a claimed task without extending the lease.

        Requires holding an active claim on the task (claim it first via
        ``claim(task_id=...)``); otherwise the API returns a 409
        :class:`DelegaAPIError`.

        Args:
            task_id: The task identifier.
            state: One of ``"working"``, ``"waiting_input"``, ``"errored"``.
            detail: Optional free-text detail (e.g. what input is needed).
        """
        body: dict[str, Any] = {"state": state}
        if detail is not None:
            body["detail"] = detail
        data = self._http.post(f"/tasks/{_seg(task_id)}/state", body=body)
        return Task.from_dict(data)

    def list_links(self, task_id: str) -> list[TaskLink]:
        """List the repo/URL links attached to a task.

        Args:
            task_id: The task identifier.
        """
        data = self._http.get(f"/tasks/{_seg(task_id)}/links")
        return [TaskLink.from_dict(l) for l in data]

    def add_link(
        self,
        task_id: str,
        kind: str,
        ref: str,
        *,
        repo: Optional[str] = None,
        url: Optional[str] = None,
    ) -> TaskLink:
        """Attach a branch, commit, PR, or URL link to a task.

        Duplicate links (same kind, repo, ref) return the existing record
        instead of creating a second one.

        Args:
            task_id: The task identifier.
            kind: One of ``"branch"``, ``"commit"``, ``"pr"``, ``"url"``.
            ref: Branch name, commit SHA, PR number, or URL reference.
            repo: Repository in ``owner/name`` form (for repo-kinded links).
            url: Optional explicit URL for the link.
        """
        body: dict[str, Any] = {"kind": kind, "ref": ref}
        if repo is not None:
            body["repo"] = repo
        if url is not None:
            body["url"] = url
        data = self._http.post(f"/tasks/{_seg(task_id)}/links", body=body)
        return TaskLink.from_dict(data)

    def delete_link(self, task_id: str, link_id: str) -> bool:
        """Remove a link from a task.

        Args:
            task_id: The task identifier.
            link_id: The link identifier.

        Returns:
            ``True`` if the link was deleted successfully.
        """
        self._http.delete(f"/tasks/{_seg(task_id)}/links/{_seg(link_id)}")
        return True

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

    def claim(
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
        ``assigned_to_agent_id``.

        Args:
            task_id: Claim this specific task instead of the next from
                the queue (raises a 409 :class:`DelegaAPIError` if it is
                not claimable). ``project_id``/``labels`` filters do not
                apply in this mode.
            project_id: Only claim tasks in this project.
            labels: Only claim tasks carrying these labels.
            lease_seconds: Lease duration in seconds, 30-3600
                (server default 300).

        Returns:
            The claimed :class:`Task`, or ``None`` if no claimable task
            is available (queue mode only).
        """
        body: dict[str, Any] = {}
        if lease_seconds is not None:
            body["lease_seconds"] = lease_seconds
        if task_id is not None:
            data = self._http.post(f"/tasks/{_seg(task_id)}/claim", body=body)
        else:
            if project_id is not None:
                body["project_id"] = project_id
            if labels is not None:
                body["labels"] = labels
            data = self._http.post("/tasks/claim", body=body)
        task = data.get("task") if isinstance(data, dict) else None
        if task is None:
            return None
        return Task.from_dict(task)

    def heartbeat(
        self, task_id: str, *, lease_seconds: Optional[int] = None
    ) -> Task:
        """Extend the lease on a task this agent has claimed.

        Args:
            task_id: The task identifier.
            lease_seconds: New lease duration in seconds, 30-3600
                (server default 300).

        Raises:
            DelegaAPIError: 409 if the caller does not hold an active
                claim on the task.
        """
        body: dict[str, Any] = {}
        if lease_seconds is not None:
            body["lease_seconds"] = lease_seconds
        data = self._http.post(f"/tasks/{_seg(task_id)}/heartbeat", body=body)
        return Task.from_dict(data)

    def release(self, task_id: str) -> Task:
        """Release a claimed task back to the queue (status ``"open"``).

        Only the claim holder or an admin may release.

        Args:
            task_id: The task identifier.

        Raises:
            DelegaAuthError: 403 if the caller is not the claim holder.
            DelegaAPIError: 409 if the task is not claimed.
        """
        data = self._http.post(f"/tasks/{_seg(task_id)}/release")
        return Task.from_dict(data)

    def add_comment(self, task_id: str, content: str) -> Comment:
        """Add a comment to a task.

        Args:
            task_id: The task identifier.
            content: The comment text.
        """
        data = self._http.post(f"/tasks/{_seg(task_id)}/comments", body={"content": content})
        return Comment.from_dict(data)

    def list_comments(self, task_id: str) -> list[Comment]:
        """List all comments on a task.

        Args:
            task_id: The task identifier.
        """
        data = self._http.get(f"/tasks/{_seg(task_id)}/comments")
        return [Comment.from_dict(c) for c in data]


class _RecurrencesNamespace:
    """Namespace for recurring task templates."""

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    def list(self) -> list[Recurrence]:
        """List recurring task templates visible to the current agent."""
        data = self._http.get("/recurrences")
        return [Recurrence.from_dict(r) for r in data]

    def create(
        self,
        content: str,
        *,
        rule_type: str,
        interval: int = 1,
        timezone: str = "UTC",
        description: Optional[str] = None,
        priority: int = 1,
        labels: Optional[list[str]] = None,
        project_id: Optional[str] = None,
        assigned_to_agent_id: Optional[str] = None,
        anchor_day: Optional[int] = None,
        anchor_month: Optional[int] = None,
        anchor_weekday: Optional[int] = None,
        next_due_at: Optional[str] = None,
        skip_if_open: Optional[bool] = None,
    ) -> Recurrence:
        """Create a recurring task template.

        Recurrences spawn normal task instances; completing an instance does
        not delete the schedule.
        """
        body: dict[str, Any] = {
            "content": content,
            "rule_type": rule_type,
            "interval": interval,
            "timezone": timezone,
        }
        optional = {
            "description": description,
            "priority": priority,
            "labels": labels,
            "project_id": project_id,
            "assigned_to_agent_id": assigned_to_agent_id,
            "anchor_day": anchor_day,
            "anchor_month": anchor_month,
            "anchor_weekday": anchor_weekday,
            "next_due_at": next_due_at,
            "skip_if_open": skip_if_open,
        }
        body.update({k: v for k, v in optional.items() if v is not None})
        data = self._http.post("/recurrences", body=body)
        return Recurrence.from_dict(data)

    def get(self, recurrence_id: str) -> Recurrence:
        """Get one recurring task template."""
        data = self._http.get(f"/recurrences/{_seg(recurrence_id)}")
        return Recurrence.from_dict(data)

    def update(self, recurrence_id: str, **fields: Any) -> Recurrence:
        """Update a recurring task template, including ``active=False`` to pause."""
        data = self._http.put(f"/recurrences/{_seg(recurrence_id)}", body=fields)
        return Recurrence.from_dict(data)

    def delete(self, recurrence_id: str) -> bool:
        """Delete a recurring task template. Spawned tasks remain."""
        self._http.delete(f"/recurrences/{_seg(recurrence_id)}")
        return True


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
        role: Optional[str] = None,
    ) -> Agent:
        """Create a new agent.

        The response includes the agent's ``api_key``, which is only
        returned at creation time.

        Args:
            name: Unique agent name.
            display_name: Optional human-friendly display name.
            description: Optional description.
            role: Optional role preset — ``"worker"`` (own-task scope,
                default), ``"coordinator"`` (sees and can comment on all
                account tasks), or ``"admin"`` (full account management).
        """
        body: dict[str, Any] = {"name": name}
        if display_name is not None:
            body["display_name"] = display_name
        if description is not None:
            body["description"] = description
        if role is not None:
            body["role"] = role
        data = self._http.post("/agents", body=body)
        return Agent.from_dict(data)

    def set_role(self, agent_id: str, role: str) -> Agent:
        """Set an agent's role (admin key required).

        Args:
            agent_id: The agent identifier.
            role: ``"worker"``, ``"coordinator"``, or ``"admin"``.
                Sandbox agents graduate via the claim flow and cannot be
                assigned a role.
        """
        data = self._http.put(f"/agents/{_seg(agent_id)}", body={"role": role})
        return Agent.from_dict(data)

    def update(self, agent_id: str, **fields: Any) -> Agent:
        """Update an agent.

        Args:
            agent_id: The agent identifier.
            **fields: Fields to update (name, display_name, description,
                role, permissions, is_admin — role changes require an
                admin key).
        """
        data = self._http.put(f"/agents/{_seg(agent_id)}", body=fields)
        return Agent.from_dict(data)

    def delete(self, agent_id: str) -> bool:
        """Delete an agent.

        Args:
            agent_id: The agent identifier.

        Returns:
            ``True`` if the agent was deleted successfully.
        """
        self._http.delete(f"/agents/{_seg(agent_id)}")
        return True

    def rotate_key(self, agent_id: str) -> dict[str, Any]:
        """Rotate an agent's API key.

        Args:
            agent_id: The agent identifier.

        Returns:
            Dictionary containing the new ``api_key``.
        """
        data = self._http.post(f"/agents/{_seg(agent_id)}/rotate-key")
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
        self._http.delete(f"/webhooks/{_seg(webhook_id)}")
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
            ``https://api.delega.dev`` (normalized to ``/v1``). To target
            a custom endpoint, use ``http://localhost:18890`` or an
            explicit ``.../api`` base URL.
        timeout: Request timeout in seconds. Defaults to 30.
        cf_access_client_id: Optional Cloudflare Access service-token client ID.
            Falls back to ``DELEGA_CF_ACCESS_CLIENT_ID``.
        cf_access_client_secret: Optional Cloudflare Access service-token secret.
            Falls back to ``DELEGA_CF_ACCESS_CLIENT_SECRET``. Both Access
            values must be configured together.

    Raises:
        DelegaError: If no API key is provided or found in the environment.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int = 30,
        cf_access_client_id: Optional[str] = None,
        cf_access_client_secret: Optional[str] = None,
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
        self._http = HTTPClient(
            base_url=base_url,
            api_key=resolved_key,
            timeout=timeout,
            access_headers=cloudflare_access_headers(
                cf_access_client_id, cf_access_client_secret
            ),
        )
        self.tasks = _TasksNamespace(self._http)
        self.recurrences = _RecurrencesNamespace(self._http)
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

        Hosted API only (``api.delega.dev``). Custom ``/api`` endpoints
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
