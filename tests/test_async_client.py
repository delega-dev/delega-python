"""Async client tests using httpx.MockTransport.

Mirrors the sync tests in test_client.py for the 1.2.0 coordination methods
(assign, delegate, chain, update_context, find_duplicates) plus the 0.2.0
usage() gate. Run with:

    pytest tests/test_async_client.py

Requires httpx + pytest-asyncio (both in dev deps).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

import httpx

from delega import (
    AsyncDelega,
    DedupResult,
    DelegaError,
    DelegationChain,
    Recurrence,
    Task,
)


def _json_handler(payload: Any, *, status: int = 200):
    """Return an httpx request handler that replies with a fixed JSON payload."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return handler


def _recording_handler(payload: Any, recorded: list[httpx.Request]):
    """Record every incoming request into ``recorded`` and reply with payload."""

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return httpx.Response(200, json=payload)

    return handler


def _make_client(handler) -> AsyncDelega:
    """Build an AsyncDelega wired to an httpx.MockTransport."""
    client = AsyncDelega(api_key="dlg_test", base_url="https://api.delega.dev")
    # Swap the transport for our mock — keeps normalize_base_url handling intact.
    transport = httpx.MockTransport(handler)
    client._http._client = httpx.AsyncClient(
        base_url=client._http._base_url,
        headers={"X-Agent-Key": "dlg_test", "User-Agent": "test"},
        transport=transport,
    )
    return client


@pytest.mark.asyncio
async def test_async_delegate_with_assignee():
    recorded: list[httpx.Request] = []
    client = _make_client(
        _recording_handler(
            {
                "id": "t_child",
                "content": "Child",
                "parent_task_id": "t1",
                "root_task_id": "t1",
                "delegation_depth": 1,
                "status": "open",
                "assigned_to_agent_id": "a2",
            },
            recorded,
        )
    )
    async with client:
        task = await client.tasks.delegate(
            "t1", "Child", assigned_to_agent_id="a2", priority=2
        )
    assert task.parent_task_id == "t1"
    assert task.delegation_depth == 1
    assert task.assigned_to_agent_id == "a2"
    assert recorded[0].url.path.endswith("/v1/tasks/t1/delegate")
    body = json.loads(recorded[0].content.decode())
    assert body["assigned_to_agent_id"] == "a2"
    assert body["priority"] == 2


@pytest.mark.asyncio
async def test_async_assign_task():
    recorded: list[httpx.Request] = []
    client = _make_client(
        _recording_handler(
            {"id": "t1", "content": "x", "assigned_to_agent_id": "a5"}, recorded
        )
    )
    async with client:
        task = await client.tasks.assign("t1", "a5")
    assert task.assigned_to_agent_id == "a5"
    assert recorded[0].method == "PUT"
    body = json.loads(recorded[0].content.decode())
    assert body == {"assigned_to_agent_id": "a5"}


@pytest.mark.asyncio
async def test_async_assign_unassign():
    recorded: list[httpx.Request] = []
    client = _make_client(
        _recording_handler({"id": "t1", "content": "x"}, recorded)
    )
    async with client:
        await client.tasks.assign("t1", None)
    body = json.loads(recorded[0].content.decode())
    assert body["assigned_to_agent_id"] is None


@pytest.mark.asyncio
async def test_async_chain_hosted_shape():
    client = _make_client(
        _json_handler(
            {
                "root_id": "abc",
                "chain": [
                    {"id": "abc", "content": "root", "delegation_depth": 0}
                ],
                "depth": 0,
                "completed_count": 0,
                "total_count": 1,
            }
        )
    )
    async with client:
        chain = await client.tasks.chain("abc")
    assert isinstance(chain, DelegationChain)
    assert chain.root_id == "abc"
    assert len(chain.chain) == 1


@pytest.mark.asyncio
async def test_async_chain_self_hosted_shape():
    """Self-hosted returns {root: Task} without root_id — client normalizes."""
    client = _make_client(
        _json_handler(
            {
                "root": {"id": 42, "content": "root"},
                "chain": [
                    {"id": 42, "content": "root", "delegation_depth": 0}
                ],
                "depth": 0,
                "completed_count": 0,
                "total_count": 1,
            }
        )
    )
    async with client:
        chain = await client.tasks.chain("42")
    assert chain.root_id == "42"


@pytest.mark.asyncio
async def test_async_update_context_hosted_bare_dict():
    recorded: list[httpx.Request] = []
    client = _make_client(
        _recording_handler({"step": "done", "count": 2}, recorded)
    )
    async with client:
        merged = await client.tasks.update_context("t1", {"count": 2})
    assert merged == {"step": "done", "count": 2}
    assert recorded[0].method == "PATCH"
    assert recorded[0].url.path.endswith("/v1/tasks/t1/context")


@pytest.mark.asyncio
async def test_async_update_context_self_hosted_full_task():
    client = _make_client(
        _json_handler(
            {
                "id": 42,
                "content": "x",
                "completed": False,
                "context": {"step": "done", "count": 2},
            }
        )
    )
    async with client:
        merged = await client.tasks.update_context("42", {"count": 2})
    assert merged == {"step": "done", "count": 2}


@pytest.mark.asyncio
async def test_async_find_duplicates():
    recorded: list[httpx.Request] = []
    client = _make_client(
        _recording_handler(
            {
                "has_duplicates": True,
                "matches": [
                    {
                        "task_id": "abc",
                        "content": "research pricing",
                        "score": 0.85,
                    }
                ],
            },
            recorded,
        )
    )
    async with client:
        result = await client.tasks.find_duplicates(
            "Research pricing", threshold=0.7
        )
    assert isinstance(result, DedupResult)
    assert result.has_duplicates
    assert len(result.matches) == 1
    assert result.matches[0].score == 0.85
    body = json.loads(recorded[0].content.decode())
    assert body == {"content": "Research pricing", "threshold": 0.7}


@pytest.mark.asyncio
async def test_async_claim_task():
    recorded: list[httpx.Request] = []
    client = _make_client(
        _recording_handler(
            {
                "task": {
                    "id": "t1",
                    "content": "Queued work",
                    "status": "claimed",
                    "claimed_by_agent_id": "a1",
                    "claimed_at": "2026-06-10T00:00:00Z",
                    "lease_expires_at": "2026-06-10T00:05:00Z",
                }
            },
            recorded,
        )
    )
    async with client:
        task = await client.tasks.claim(
            project_id="p1", labels=["worker"], lease_seconds=120
        )
    assert isinstance(task, Task)
    assert task.status == "claimed"
    assert task.claimed_by_agent_id == "a1"
    assert task.claimed_at == "2026-06-10T00:00:00Z"
    assert task.lease_expires_at == "2026-06-10T00:05:00Z"
    assert recorded[0].url.path.endswith("/v1/tasks/claim")
    body = json.loads(recorded[0].content.decode())
    assert body == {"project_id": "p1", "labels": ["worker"], "lease_seconds": 120}


@pytest.mark.asyncio
async def test_async_claim_task_empty_queue_returns_none():
    recorded: list[httpx.Request] = []
    client = _make_client(_recording_handler({"task": None}, recorded))
    async with client:
        task = await client.tasks.claim()
    assert task is None
    # No optional filters supplied — body should be empty JSON.
    body = json.loads(recorded[0].content.decode())
    assert body == {}


@pytest.mark.asyncio
async def test_async_heartbeat_task():
    recorded: list[httpx.Request] = []
    client = _make_client(
        _recording_handler(
            {
                "id": "t1",
                "content": "Queued work",
                "status": "claimed",
                "claimed_by_agent_id": "a1",
                "lease_expires_at": "2026-06-10T00:10:00Z",
            },
            recorded,
        )
    )
    async with client:
        task = await client.tasks.heartbeat("t1", lease_seconds=600)
    assert task.lease_expires_at == "2026-06-10T00:10:00Z"
    assert recorded[0].url.path.endswith("/v1/tasks/t1/heartbeat")
    body = json.loads(recorded[0].content.decode())
    assert body == {"lease_seconds": 600}


@pytest.mark.asyncio
async def test_async_release_task():
    recorded: list[httpx.Request] = []
    client = _make_client(
        _recording_handler(
            {
                "id": "t1",
                "content": "Queued work",
                "status": "open",
                "claimed_by_agent_id": None,
                "claimed_at": None,
                "lease_expires_at": None,
            },
            recorded,
        )
    )
    async with client:
        task = await client.tasks.release("t1")
    assert task.status == "open"
    assert task.claimed_by_agent_id is None
    assert recorded[0].url.path.endswith("/v1/tasks/t1/release")


@pytest.mark.asyncio
async def test_async_list_tasks_claimed_filter():
    recorded: list[httpx.Request] = []
    client = _make_client(_recording_handler([], recorded))
    async with client:
        await client.tasks.list(claimed=True)
        await client.tasks.list(claimed=False)
        await client.tasks.list()
    assert recorded[0].url.params["claimed"] == "true"
    assert recorded[1].url.params["claimed"] == "false"
    assert "claimed" not in recorded[2].url.params


@pytest.mark.asyncio
async def test_async_usage_hosted():
    recorded: list[httpx.Request] = []
    client = _make_client(
        _recording_handler(
            {
                "plan": "free",
                "task_count_month": 42,
                "task_limit": 1000,
                "rate_limit_rpm": 60,
            },
            recorded,
        )
    )
    async with client:
        result = await client.usage()
    assert result["plan"] == "free"
    assert recorded[0].url.path.endswith("/v1/usage")


@pytest.mark.asyncio
async def test_async_usage_self_hosted_raises_before_fetch():
    """Self-hosted should raise DelegaError without touching the transport."""
    recorded: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return httpx.Response(200, json={})

    client = AsyncDelega(
        api_key="dlg_test", base_url="http://127.0.0.1:18890"
    )
    client._http._client = httpx.AsyncClient(
        base_url=client._http._base_url,
        headers={"X-Agent-Key": "dlg_test"},
        transport=httpx.MockTransport(handler),
    )
    async with client:
        with pytest.raises(DelegaError) as ctx:
            await client.usage()
    assert "only available on the hosted" in str(ctx.value)
    assert not recorded, "transport should not have been called"


@pytest.mark.asyncio
async def test_async_accepts_DELEGA_AGENT_KEY_fallback(monkeypatch):
    """Agent-side env-var consistency with @delega-dev/mcp."""
    monkeypatch.delenv("DELEGA_API_KEY", raising=False)
    monkeypatch.setenv("DELEGA_AGENT_KEY", "dlg_from_agent_env")
    client = AsyncDelega()
    assert client._http._api_key == "dlg_from_agent_env"


@pytest.mark.asyncio
async def test_async_update_context_versioned_wrapper():
    recorded: list[httpx.Request] = []
    client = _make_client(
        _recording_handler({"context": {"k": 1, "j": 2}, "version": 4}, recorded)
    )
    async with client:
        merged = await client.tasks.update_context(
            "t1", {"k": 1}, source="agent_observed", expected_version=3
        )
    assert merged == {"k": 1, "j": 2}
    assert recorded[0].url.path.endswith("/v1/tasks/t1/context")
    assert recorded[0].url.params["source"] == "agent_observed"
    assert recorded[0].url.params["expected_version"] == "3"


@pytest.mark.asyncio
async def test_async_get_context_with_provenance():
    recorded: list[httpx.Request] = []
    client = _make_client(
        _recording_handler(
            {
                "context": {"notes": "hi"},
                "version": 2,
                "provenance": {"notes": {"source": "agent_inferred"}},
            },
            recorded,
        )
    )
    async with client:
        snap = await client.tasks.get_context("t1", include_provenance=True)
    assert snap.context == {"notes": "hi"}
    assert snap.version == 2
    assert snap.provenance is not None
    assert recorded[0].url.params["include"] == "provenance"


@pytest.mark.asyncio
async def test_async_context_history():
    client = _make_client(
        _json_handler(
            {
                "entries": [
                    {"id": "ce1", "key": "notes", "value": 1, "version": 1},
                ],
                "next_cursor": None,
            }
        )
    )
    async with client:
        history = await client.tasks.context_history("t1", key="notes")
    assert len(history.entries) == 1
    assert history.entries[0].key == "notes"
    assert history.next_cursor is None


@pytest.mark.asyncio
async def test_async_supersede_context():
    recorded: list[httpx.Request] = []
    client = _make_client(
        _recording_handler(
            {"superseded": {"id": "ce1", "key": "notes", "value": "x", "version": 1}},
            recorded,
        )
    )
    async with client:
        entry = await client.tasks.supersede_context("t1", "notes")
    assert entry.key == "notes"
    body = json.loads(recorded[0].content.decode())
    assert body == {"key": "notes"}


@pytest.mark.asyncio
async def test_async_set_state():
    recorded: list[httpx.Request] = []
    client = _make_client(
        _recording_handler(
            {"id": "t1", "content": "Work", "session_state": "errored",
             "session_state_detail": "boom"},
            recorded,
        )
    )
    async with client:
        task = await client.tasks.set_state("t1", "errored", detail="boom")
    assert task.session_state == "errored"
    assert recorded[0].url.path.endswith("/v1/tasks/t1/state")
    body = json.loads(recorded[0].content.decode())
    assert body == {"state": "errored", "detail": "boom"}


@pytest.mark.asyncio
async def test_async_task_links_roundtrip():
    recorded: list[httpx.Request] = []
    client = _make_client(
        _recording_handler(
            {"id": "lnk1", "task_id": "t1", "kind": "branch", "ref": "main"},
            recorded,
        )
    )
    async with client:
        link = await client.tasks.add_link("t1", "branch", "main")
    assert link.kind == "branch"
    assert recorded[0].url.path.endswith("/v1/tasks/t1/links")

    client2 = _make_client(
        _json_handler([
            {"id": "lnk1", "task_id": "t1", "kind": "branch", "ref": "main"},
        ])
    )
    async with client2:
        links = await client2.tasks.list_links("t1")
    assert len(links) == 1

    recorded3: list[httpx.Request] = []
    client3 = _make_client(_recording_handler({"ok": True}, recorded3))
    async with client3:
        assert await client3.tasks.delete_link("t1", "lnk1") is True
    assert recorded3[0].method == "DELETE"
    assert recorded3[0].url.path.endswith("/v1/tasks/t1/links/lnk1")


@pytest.mark.asyncio
async def test_async_recurrences_roundtrip():
    payload = {
        "id": "rec1",
        "content": "Replace furnace filter",
        "priority": 1,
        "labels": "[\"home-family\"]",
        "rule_type": "monthly",
        "interval": 1,
        "timezone": "America/Chicago",
        "anchor_day": 1,
        "next_due_at": "2026-07-01T05:00:00.000Z",
        "active": 1,
        "skip_if_open": 1,
    }

    client = _make_client(_json_handler([payload]))
    async with client:
        recurrences = await client.recurrences.list()
    assert len(recurrences) == 1
    assert isinstance(recurrences[0], Recurrence)
    assert recurrences[0].labels == ["home-family"]

    recorded: list[httpx.Request] = []
    client2 = _make_client(_recording_handler(payload, recorded))
    async with client2:
        recurrence = await client2.recurrences.create(
            "Replace furnace filter",
            rule_type="monthly",
            timezone="America/Chicago",
            anchor_day=1,
            labels=["home-family"],
        )
    assert recurrence.id == "rec1"
    assert recorded[0].method == "POST"
    assert recorded[0].url.path.endswith("/v1/recurrences")
    body = json.loads(recorded[0].content.decode())
    assert body["rule_type"] == "monthly"
    assert body["labels"] == ["home-family"]

    recorded2: list[httpx.Request] = []
    client3 = _make_client(_recording_handler({**payload, "active": 0}, recorded2))
    async with client3:
        recurrence = await client3.recurrences.update("rec1", active=False)
    assert recurrence.active == 0
    assert recorded2[0].method == "PUT"
    assert recorded2[0].url.path.endswith("/v1/recurrences/rec1")

    recorded3: list[httpx.Request] = []
    client4 = _make_client(_recording_handler({"ok": True}, recorded3))
    async with client4:
        assert await client4.recurrences.delete("rec1") is True
    assert recorded3[0].method == "DELETE"
    assert recorded3[0].url.path.endswith("/v1/recurrences/rec1")
