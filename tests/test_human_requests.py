"""Exercise both real SDK transports; fixtures contain no live credentials."""
import io
import json
from functools import partial
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlparse

import httpx
import pytest

from delega import AsyncDelega, Delega, HumanRequest, DelegaNotFoundError
from delega.models import Task

TASK_ID = "d" * 32
VIEW = dict(
    task_id=TASK_ID, kind="checklist", recipient_ref="self", criteria=["Room checked"],
    phase="prepared", version=0, task_revision=4, expected_revision=4, task_digest="a" * 64,
    timeout_seconds=1200, maximum_prompts=2, policy_version="checklist-attestation-v1",
    task_status="open", result=None, answers=[],
)


@pytest.mark.asyncio
async def test_sync_async_human_requests_have_identical_wire_contracts():
    seen_sync, seen_async = [], []
    def urlopen(request, **_kwargs):
        seen_sync.append((request.method, urlparse(request.full_url).path,
                          json.loads(request.data) if request.data else None))
        return io.BytesIO(json.dumps(VIEW).encode())
    def handle(request):
        seen_async.append((request.method, request.url.path,
                           json.loads(request.content) if request.content else None))
        return httpx.Response(200, json=VIEW)
    with patch("urllib.request.urlopen", urlopen):
        client = Delega(api_key="dlg_synthetic")
        registered = client.tasks.request_human(TASK_ID, criteria=["Room checked"], expected_revision=4)
        assert isinstance(registered, HumanRequest)
        assert registered.result is None
        assert client.tasks.human_request(TASK_ID).version == 0
        assert client.tasks.human_result(TASK_ID).result is None
        client.tasks.cancel_human_request(TASK_ID, expected_version=0)
    with patch("httpx.AsyncClient", partial(httpx.AsyncClient, transport=httpx.MockTransport(handle), trust_env=False)):
        async with AsyncDelega(api_key="dlg_synthetic") as client:
            await client.tasks.request_human(TASK_ID, criteria=["Room checked"], expected_revision=4)
            await client.tasks.human_request(TASK_ID)
            await client.tasks.human_result(TASK_ID)
            await client.tasks.cancel_human_request(TASK_ID, expected_version=0)
    assert seen_sync == seen_async
    assert seen_sync == [
        ("POST", f"/v1/tasks/{TASK_ID}/human-request",
         dict(kind="checklist", recipient_ref="self", criteria=["Room checked"], expected_revision=4, timeout_seconds=1200)),
        ("GET", f"/v1/tasks/{TASK_ID}/human-request", None),
        ("GET", f"/v1/tasks/{TASK_ID}/human-request/result", None),
        ("POST", f"/v1/tasks/{TASK_ID}/human-request/cancel", {"expected_version": 0}),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"criteria": []}, {"criteria": ["x / y"]}, {"criteria": ["same", "same"]},
    {"criteria": ["🏀" * 33]}, {"expected_revision": True}, {"expected_revision": -1},
    {"timeout_seconds": 1201}, {"task_id": "../agents"},
])
async def test_invalid_input_fails_before_either_transport(change):
    values = dict(task_id=TASK_ID, criteria=["Ready"], expected_revision=0)
    values.update(change)
    with patch("urllib.request.urlopen") as request:
        with pytest.raises(ValueError):
            Delega(api_key="dlg_synthetic").tasks.request_human(**values)
        request.assert_not_called()
    with patch("httpx.AsyncClient.request") as request:
        async with AsyncDelega(api_key="dlg_synthetic") as client:
            with pytest.raises(ValueError):
                await client.tasks.request_human(**values)
        request.assert_not_called()


@pytest.mark.asyncio
async def test_task_creation_and_completion_keep_evidence_and_fences_in_both_clients():
    response = dict(id=TASK_ID, content="Room readiness", revision=12, claim_generation=3, evidence_policy="required")
    sync, asynchronous = [], []
    def urlopen(request, **_kwargs):
        sync.append(json.loads(request.data) if request.data else None)
        return io.BytesIO(json.dumps(response).encode())
    def handle(request):
        asynchronous.append(json.loads(request.content) if request.content else None)
        return httpx.Response(200, json=response)
    evidence = [{"kind": "artifact_url", "ref": "https://example.test/retained-result"}]
    with patch("urllib.request.urlopen", urlopen):
        client = Delega(api_key="dlg_synthetic")
        task = client.tasks.create("Room readiness", labels=["autopilot-hold"],
                                  assigned_to_agent_id="agt_existing", evidence_policy="required")
        assert task.revision == 12 and task.claim_generation == 3
        client.tasks.complete(TASK_ID, evidence=evidence, expected_revision=12, claim_generation=3)
        client.tasks.complete(TASK_ID)
    with patch("httpx.AsyncClient", partial(httpx.AsyncClient, transport=httpx.MockTransport(handle), trust_env=False)):
        async with AsyncDelega(api_key="dlg_synthetic") as client:
            await client.tasks.create("Room readiness", labels=["autopilot-hold"],
                                      assigned_to_agent_id="agt_existing", evidence_policy="required")
            await client.tasks.complete(TASK_ID, evidence=evidence, expected_revision=12, claim_generation=3)
            await client.tasks.complete(TASK_ID)
    assert sync == asynchronous
    assert sync[0]["assigned_to_agent_id"] == "agt_existing"
    assert sync[0]["evidence_policy"] == "required"
    assert sync[1] == dict(evidence=evidence, expected_revision=12, claim_generation=3)
    assert sync[2] is None


def test_request_model_preserves_server_attestation_without_inventing_proof():
    proof = dict(verification="human_attested", physical_state_independently_verified=False)
    result = HumanRequest.from_dict({**VIEW, "phase": "completed", "result": proof, "future_field": "ignored"})
    assert result.result == proof
    assert HumanRequest.from_dict(VIEW).result is None
    legacy = Task.from_dict({"id": TASK_ID, "content": "Legacy"})
    assert legacy.revision is None and legacy.claim_generation is None


@pytest.mark.asyncio
async def test_disabled_feature_errors_are_returned_without_fallback_or_task_creation():
    error = HTTPError("https://api.delega.dev/v1/tasks/" + TASK_ID + "/human-request", 404, "missing", {},
                      io.BytesIO(b'{"error":"Not found"}'))
    with patch("urllib.request.urlopen", side_effect=error) as request:
        with pytest.raises(DelegaNotFoundError):
            Delega(api_key="dlg_synthetic").tasks.request_human(TASK_ID, criteria=["Ready"], expected_revision=0)
        assert request.call_count == 1
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(404, json={"error": "Not found"})
    with patch("httpx.AsyncClient", partial(httpx.AsyncClient, transport=httpx.MockTransport(handle), trust_env=False)):
        async with AsyncDelega(api_key="dlg_synthetic") as client:
            with pytest.raises(DelegaNotFoundError):
                await client.tasks.request_human(TASK_ID, criteria=["Ready"], expected_revision=0)
    assert len(calls) == 1
