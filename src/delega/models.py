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
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        """Create a Task from an API response dictionary."""
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
    api_key: Optional[str] = None
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
