"""With no ``cors_allow_origins`` the host registers no API policy (#527)."""

from __future__ import annotations

import httpx

ORIGIN = "https://app.example.com"


async def test_no_origins_means_no_cors_headers(client: httpx.AsyncClient):
    resp = await client.options(
        "/api/anything",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in resp.headers


async def test_no_host_policy_registered(app):
    assert app.state.cors_policies.match("GET", "/api/anything") is None
