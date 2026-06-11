"""Data models for the Delega SDK."""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from typing import Any, Optional


def _normalize_merged_context(data: Any) -> dict[str, Any]:
    """Normalize a ``PATCH /tasks/:id/context`` response to the merged dict.

    The hosted API returns ``{"context": {...}, "version": N}``; custom
    ``/api``-style endpoints return the full Task; older servers returned
    the bare merged dict. Always hand callers the merged context.
    """
    if not isinstance(data, dict):
        return {}
    if "context" in data and "version" in data and "id" not in data:
        ctx = data["context"]
        return ctx if isinstance(ctx, dict) else {}
    if "content" in data and "id" in data:
        raw_ctx = data.get("context") or {}
        if isinstance(raw_ctx, str):
            try:
                raw_ctx = _json.loads(raw_ctx) if raw_ctx.strip() else {}
            except Exception:
                raw_ctx = {}
        return raw_ctx if isinstance(raw_ctx, dict) else {}
    return data


@dataclass
class Task:
    """A Delega task."""

    id: str
    content: str
    description: Optional[str] = None
    priority: int = 2
    labels: list[str] = field(default_factory=list)
    due_date: Optional[str] = None
    completed: bool = False
    project_id: Optional[str] = None
    parent_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    root_task_id: Optional[str] = None
    delegation_depth: int = 0
    status: Optional[str] = None
    assigned_to_agent_id: Optional[str] = None
    created_by_agent_id: Optional[str] = None
    completed_by_agent_id: Optional[str] = None
    claimed_by_agent_id: Optional[str] = None
    claimed_at: Optional[str] = None
    lease_expires_at: Optional[str] = None
    session_state: Optional[str] = None
    session_state_detail: Optional[str] = None
    accountable_agent_id: Optional[str] = None
    context: Optional[dict[str, Any]] = None
    context_version: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        """Create a Task from an API response dictionary."""
        # `context` ships as a JSON-encoded string on hosted (D1/SQLite)
        # and a dict on self-hosted (SQLAlchemy JSON). Normalize to dict.
        import json as _json
        raw_ctx = data.get("context")
        if isinstance(raw_ctx, str):
            try:
                raw_ctx = _json.loads(raw_ctx) if raw_ctx.strip() else None
            except Exception:
                raw_ctx = None
        return cls(
            id=data["id"],
            content=data["content"],
            description=data.get("description"),
            priority=data.get("priority", 2),
            labels=data.get("labels", []),
            due_date=data.get("due_date"),
            completed=data.get("completed", False),
            project_id=data.get("project_id"),
            parent_id=data.get("parent_id"),
            parent_task_id=data.get("parent_task_id"),
            root_task_id=data.get("root_task_id"),
            delegation_depth=data.get("delegation_depth", 0) or 0,
            status=data.get("status"),
            assigned_to_agent_id=data.get("assigned_to_agent_id"),
            created_by_agent_id=data.get("created_by_agent_id"),
            completed_by_agent_id=data.get("completed_by_agent_id"),
            claimed_by_agent_id=data.get("claimed_by_agent_id"),
            claimed_at=data.get("claimed_at"),
            lease_expires_at=data.get("lease_expires_at"),
            session_state=data.get("session_state"),
            session_state_detail=data.get("session_state_detail"),
            accountable_agent_id=data.get("accountable_agent_id"),
            context=raw_ctx if isinstance(raw_ctx, dict) else None,
            context_version=data.get("context_version", 0) or 0,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class Comment:
    """A comment on a Delega task."""

    id: str
    task_id: str
    content: str
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Comment:
        """Create a Comment from an API response dictionary."""
        return cls(
            id=data["id"],
            task_id=data["task_id"],
            content=data["content"],
            created_at=data.get("created_at"),
        )


@dataclass
class Agent:
    """A Delega agent."""

    id: str
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    api_key: Optional[str] = field(default=None, repr=False)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Agent:
        """Create an Agent from an API response dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            display_name=data.get("display_name"),
            description=data.get("description"),
            api_key=data.get("api_key"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class Project:
    """A Delega project."""

    id: str
    name: str
    emoji: Optional[str] = None
    color: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        """Create a Project from an API response dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            emoji=data.get("emoji"),
            color=data.get("color"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class DelegationChain:
    """The full parent/child delegation chain for a task.

    Normalized across hosted (returns ``root_id: str``) and self-hosted
    (returns ``root: Task``) response shapes — the client layer ensures
    ``root_id`` is always populated.
    """

    root_id: str
    chain: list[Task] = field(default_factory=list)
    depth: int = 0
    completed_count: int = 0
    total_count: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DelegationChain:
        """Create a DelegationChain from an API response dictionary."""
        # Hosted: {root_id, chain, ...}. Self-hosted: {root: Task, chain, ...}.
        root_id = data.get("root_id")
        if root_id is None:
            root = data.get("root")
            if isinstance(root, dict):
                root_id = root.get("id")
        chain_raw = data.get("chain") or []
        return cls(
            root_id=str(root_id) if root_id is not None else "",
            chain=[Task.from_dict(t) for t in chain_raw if isinstance(t, dict)],
            depth=data.get("depth", 0) or 0,
            completed_count=data.get("completed_count", 0) or 0,
            total_count=data.get("total_count", 0) or 0,
        )


@dataclass
class TaskLink:
    """A link attaching repo activity (branch/commit/PR) or a URL to a task."""

    id: str
    task_id: str
    kind: str
    ref: str
    repo: Optional[str] = None
    url: Optional[str] = None
    created_by_agent_id: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskLink:
        """Create a TaskLink from an API response dictionary."""
        return cls(
            id=data["id"],
            task_id=data["task_id"],
            kind=data["kind"],
            ref=data["ref"],
            repo=data.get("repo"),
            url=data.get("url"),
            created_by_agent_id=data.get("created_by_agent_id"),
            created_at=data.get("created_at"),
        )


@dataclass
class ContextEntry:
    """One entry in a task's append-only context provenance ledger."""

    id: str
    key: str
    value: Any
    version: int
    source: Optional[str] = None
    author_agent_id: Optional[str] = None
    author_name: Optional[str] = None
    created_at: Optional[str] = None
    superseded_by: Optional[str] = None
    superseded_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextEntry:
        """Create a ContextEntry from an API response dictionary."""
        return cls(
            id=str(data["id"]),
            key=data["key"],
            value=data.get("value"),
            version=int(data.get("version", 0) or 0),
            source=data.get("source"),
            author_agent_id=data.get("author_agent_id"),
            author_name=data.get("author_name"),
            created_at=data.get("created_at"),
            superseded_by=data.get("superseded_by"),
            superseded_at=data.get("superseded_at"),
        )


@dataclass
class ContextSnapshot:
    """A task's current context blob, its version, and optional provenance.

    ``provenance`` maps each live context key to author/source metadata and
    is only populated when requested with ``include_provenance=True``.
    """

    context: dict[str, Any] = field(default_factory=dict)
    version: int = 0
    provenance: Optional[dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextSnapshot:
        """Create a ContextSnapshot from an API response dictionary."""
        ctx = data.get("context")
        return cls(
            context=ctx if isinstance(ctx, dict) else {},
            version=int(data.get("version", 0) or 0),
            provenance=data.get("provenance"),
        )


@dataclass
class ContextHistory:
    """A page of the context provenance ledger.

    ``next_cursor`` is ``None`` on the last page; pass it back as
    ``cursor=`` to fetch the next page otherwise.
    """

    entries: list[ContextEntry] = field(default_factory=list)
    next_cursor: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextHistory:
        """Create a ContextHistory from an API response dictionary."""
        return cls(
            entries=[
                ContextEntry.from_dict(e)
                for e in (data.get("entries") or [])
                if isinstance(e, dict)
            ],
            next_cursor=data.get("next_cursor"),
        )


@dataclass
class DuplicateMatch:
    """A single duplicate-match result from ``find_duplicates``."""

    task_id: str
    content: str
    score: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DuplicateMatch:
        """Create a DuplicateMatch from an API response dictionary."""
        return cls(
            task_id=str(data["task_id"]),
            content=data["content"],
            score=float(data.get("score", 0.0)),
        )


@dataclass
class DedupResult:
    """Result of calling ``tasks.find_duplicates``."""

    has_duplicates: bool
    matches: list[DuplicateMatch] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DedupResult:
        """Create a DedupResult from an API response dictionary."""
        return cls(
            has_duplicates=bool(data.get("has_duplicates", False)),
            matches=[
                DuplicateMatch.from_dict(m)
                for m in (data.get("matches") or [])
                if isinstance(m, dict)
            ],
        )
