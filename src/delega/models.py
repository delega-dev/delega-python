"""Data models for the Delega SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


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
    context: Optional[dict[str, Any]] = None
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
            context=raw_ctx if isinstance(raw_ctx, dict) else None,
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
