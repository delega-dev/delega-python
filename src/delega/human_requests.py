"""Typed, inert adapters for the API's private human-request contract."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from typing import Any, Optional


@dataclass
class HumanRequest:
    """Server-reported state; the SDK never derives or upgrades verification."""

    task_id: str
    kind: str
    recipient_ref: str
    criteria: list[str]
    phase: str
    version: int
    task_revision: int
    expected_revision: int
    task_digest: str
    timeout_seconds: int
    maximum_prompts: int
    policy_version: str
    task_status: str
    result: Optional[dict[str, Any]] = None
    answers: list[dict[str, Any]] = field(default_factory=list)
    started_at: Optional[str] = None
    expires_at: Optional[str] = None
    execution_claim_generation: Optional[int] = None
    cancel_requested_at: Optional[str] = None
    replayed: Optional[bool] = None
    activation: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HumanRequest:
        names = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in names})


def request_path(task_id: str) -> str:
    if not isinstance(task_id, str) or not re.fullmatch(r"[a-f0-9]{32}", task_id):
        raise ValueError("human requests require an exact internal task ID")
    return f"/tasks/{task_id}/human-request"


def nonnegative_integer(value: int, name: str) -> int:
    if type(value) is not int or not 0 <= value <= 9_007_199_254_740_991:
        raise ValueError(f"{name} must be a non-negative safe integer")
    return value


def registration_body(criteria: list[str], expected_revision: int, timeout_seconds: int) -> dict[str, Any]:
    nonnegative_integer(expected_revision, "expected_revision")
    if type(timeout_seconds) is not int or not 60 <= timeout_seconds <= 1200:
        raise ValueError("timeout_seconds must be between 60 and 1200")
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= 3:
        raise ValueError("use one to three criteria")
    if any(not isinstance(item, str) or not item.strip() or len(item.encode("utf-16-le")) // 2 > 65
           or "\r" in item or "\n" in item or " / " in item for item in criteria):
        raise ValueError("criteria must be short nonblank strings without line breaks or option delimiters")
    if len(set(criteria)) != len(criteria):
        raise ValueError("criteria must be distinct")
    return dict(kind="checklist", recipient_ref="self", criteria=criteria,
                expected_revision=expected_revision, timeout_seconds=timeout_seconds)


def completion_body(evidence, expected_revision, claim_generation):
    body = {}
    if evidence is not None:
        body["evidence"] = evidence
    for name, value in (("expected_revision", expected_revision), ("claim_generation", claim_generation)):
        if value is not None:
            body[name] = nonnegative_integer(value, name)
    return body or None
