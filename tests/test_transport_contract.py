"""Exercise the same wire contracts through the two real SDK transports."""

import io
from functools import partial
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import httpx
import pytest

from delega import AsyncDelega, Delega, DelegaAPIError, DelegaAuthError, DelegaNotFoundError, DelegaRateLimitError


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [True, False, None])
async def test_task_filter_booleans_match_between_transports(value):
    seen = []

    def urlopen(request, **kwargs):
        seen.append(request.full_url)
        return io.BytesIO(b"[]")

    with patch("urllib.request.urlopen", urlopen):
        Delega(api_key="dlg_fixture").tasks.list(completed=value, claimed=value)

    def handle(request):
        seen.append(str(request.url))
        return httpx.Response(200, json=[])

    with patch("httpx.AsyncClient", partial(httpx.AsyncClient, transport=httpx.MockTransport(handle), trust_env=False)):
        async with AsyncDelega(api_key="dlg_fixture") as client:
            await client.tasks.list(completed=value, claimed=value)

    expected = {} if value is None else {"completed": [str(value).lower()], "claimed": [str(value).lower()]}
    assert len(seen) == 2
    for url in seen:
        assert urlparse(url).path == "/v1/tasks"
        assert parse_qs(urlparse(url).query) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("status,kind", [(401, DelegaAuthError), (403, DelegaAuthError), (404, DelegaNotFoundError), (429, DelegaRateLimitError), (503, DelegaAPIError)])
@pytest.mark.parametrize("body,message", [
    ('{"error":"denied"}', "denied"),
    ('{"error":{"code":"forbidden","message":"denied"}}', "denied"),
    ('[]', '[]'),
    ('null', 'null'),
    ('upstream unavailable', 'upstream unavailable'),
])
async def test_error_classification_survives_nonstandard_bodies(status, kind, body, message):
    error = HTTPError("https://api.delega.dev/v1/tasks", status, "failure", {}, io.BytesIO(body.encode()))
    with patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(kind) as sync_error:
            Delega(api_key="dlg_fixture").tasks.list()

    def handle(request):
        return httpx.Response(status, text=body)

    with patch("httpx.AsyncClient", partial(httpx.AsyncClient, transport=httpx.MockTransport(handle), trust_env=False)):
        async with AsyncDelega(api_key="dlg_fixture") as client:
            with pytest.raises(kind) as async_error:
                await client.tasks.list()

    for raised in (sync_error, async_error):
        assert type(raised.value) is kind
        assert raised.value.status_code == status
        assert raised.value.error_message == message
