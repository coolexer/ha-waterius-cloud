"""Tests for the Waterius cloud HTTP client."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import aiohttp
import pytest
from aioresponses import aioresponses

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "waterius_cloud"))

import api  # noqa: E402

BASE = "https://account.waterius.ru"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as client:
        yield client


async def test_get_user_returns_payload(session):
    with aioresponses() as mocked:
        mocked.get(f"{BASE}/api/user/", payload={"user": 13382, "email": "a@b.ru"})
        client = api.WateriusApi(session, "tok")

        assert await client.get_user() == {"user": 13382, "email": "a@b.ru"}


async def test_get_user_sends_the_token(session):
    with aioresponses() as mocked:
        mocked.get(f"{BASE}/api/user/", payload={"user": 1})
        client = api.WateriusApi(session, "tok")
        await client.get_user()

        request = next(iter(mocked.requests.values()))[0]
        assert request.kwargs["headers"]["Authorization"] == "Token tok"


async def test_get_sources_follows_pagination(session):
    with aioresponses() as mocked:
        mocked.get(
            f"{BASE}/api/source/?page=1",
            payload={"next": f"{BASE}/api/source/?page=2", "results": [{"id": 1}]},
        )
        mocked.get(
            f"{BASE}/api/source/?page=2",
            payload={"next": None, "results": [{"id": 2}]},
        )
        client = api.WateriusApi(session, "tok")

        assert await client.get_sources() == [{"id": 1}, {"id": 2}]


async def test_real_payload_round_trips(session):
    body = json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))
    with aioresponses() as mocked:
        mocked.get(f"{BASE}/api/source/?page=1", payload=body)
        client = api.WateriusApi(session, "tok")

        sources = await client.get_sources()

        assert len(sources) == 1
        assert sources[0]["id"] == 35488


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_errors_raise_auth_error(session, status):
    with aioresponses() as mocked:
        mocked.get(f"{BASE}/api/user/", status=status, payload={"detail": "нет"})
        client = api.WateriusApi(session, "tok")

        with pytest.raises(api.WateriusAuthError):
            await client.get_user()


async def test_server_error_raises_connection_error(session):
    with aioresponses() as mocked:
        mocked.get(f"{BASE}/api/user/", status=500)
        client = api.WateriusApi(session, "tok")

        with pytest.raises(api.WateriusConnectionError):
            await client.get_user()


async def test_network_failure_raises_connection_error(session):
    with aioresponses() as mocked:
        mocked.get(f"{BASE}/api/user/", exception=aiohttp.ClientError("boom"))
        client = api.WateriusApi(session, "tok")

        with pytest.raises(api.WateriusConnectionError):
            await client.get_user()


async def test_refresh_source_posts_to_the_update_endpoint(session):
    with aioresponses() as mocked:
        mocked.get(f"{BASE}/api/source/35488/update", payload={})
        client = api.WateriusApi(session, "tok")

        await client.refresh_source(35488)


async def test_refresh_source_reports_the_cooldown(session):
    with aioresponses() as mocked:
        mocked.get(
            f"{BASE}/api/source/35488/update",
            status=429,
            headers={"Retry-After": "45"},
            payload={"message": "Подождите"},
        )
        client = api.WateriusApi(session, "tok")

        with pytest.raises(api.WateriusRateLimitError) as excinfo:
            await client.refresh_source(35488)

        assert excinfo.value.retry_after == 45
