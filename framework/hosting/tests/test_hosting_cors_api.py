"""Configurable CORS on the host API (#527): preflight, allowlist, 413 headers."""

from __future__ import annotations

import httpx
import pytest
from simple_module_hosting.settings import Settings

ALLOWED = "https://app.example.com"
OTHER = "https://evil.example.com"
BODY_LIMIT = 1000


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"cors_allow_origins": [ALLOWED], "max_request_body_bytes": BODY_LIMIT}
    )


def _preflight(origin: str) -> dict[str, str]:
    return {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    }


async def test_preflight_from_allowed_origin_never_reaches_auth(client: httpx.AsyncClient):
    resp = await client.options("/api/anything", headers=_preflight(ALLOWED))
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == ALLOWED
    assert resp.headers["access-control-allow-credentials"] == "true"
    assert "authorization" in resp.headers["access-control-allow-headers"].lower()


async def test_other_origin_gets_no_allow_origin_on_api(client: httpx.AsyncClient):
    resp = await client.get("/api/anything", headers={"Origin": OTHER})
    assert "access-control-allow-origin" not in resp.headers
    pre = await client.options("/api/anything", headers=_preflight(OTHER))
    assert "access-control-allow-origin" not in pre.headers


async def test_simple_request_from_allowed_origin_carries_headers(client: httpx.AsyncClient):
    resp = await client.get("/api/anything", headers={"Origin": ALLOWED})
    assert resp.headers["access-control-allow-origin"] == ALLOWED


async def test_paths_outside_api_are_untouched(client: httpx.AsyncClient):
    resp = await client.get("/health", headers={"Origin": ALLOWED})
    assert "access-control-allow-origin" not in resp.headers


async def test_413_from_body_limit_still_carries_cors(client: httpx.AsyncClient):
    resp = await client.post(
        "/api/anything",
        content=b"x" * (BODY_LIMIT + 1),
        headers={"Origin": ALLOWED, "Accept": "application/json"},
    )
    assert resp.status_code == 413
    assert resp.headers["access-control-allow-origin"] == ALLOWED
