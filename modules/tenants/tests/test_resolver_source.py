"""``request.state.tenant_source`` and ``Vary`` from the tenants resolver."""

from __future__ import annotations

import httpx
import pytest
from fastapi import Request
from tenants.host_resolver import forget_hosts


@pytest.fixture
async def probe(app):
    async def route(request: Request):
        s = request.state
        return {
            "tenant": getattr(s, "tenant_id", None),
            "source": getattr(s, "tenant_source", None),
        }

    app.add_api_route("/probe", route, methods=["GET"])
    app.state.public_routes.add_prefix("/probe", methods={"GET"})
    yield app
    app.state.tenants.settings.subdomain_base = ""
    forget_hosts()


def _vary(resp) -> list[str]:
    return [t.strip().lower() for t in resp.headers.get("vary", "").split(",") if t.strip()]


async def _create(client, name):
    return (await client.post("/api/tenants/", json={"name": name})).json()


async def test_session_source(probe, user_client):
    async with user_client("a@x.io") as (a, _):
        t = await _create(a, "One")
        body = (await a.get("/probe")).json()
        assert body == {"tenant": t["id"], "source": "session"}


async def test_header_source_and_vary(probe, user_client):
    async with user_client("a@x.io") as (a, _):
        t = await _create(a, "One")
        resp = await a.get("/probe", headers={"X-Tenant-ID": t["id"]})
        assert resp.json()["source"] == "header"
        assert "x-tenant-id" in _vary(resp)


async def test_unresolved_header_has_no_source_but_varies(probe, user_client):
    async with user_client("a@x.io") as (a, _):
        await _create(a, "One")
        resp = await a.get("/probe", headers={"X-Tenant-ID": "nope"})
        assert resp.json()["source"] is None
        assert "x-tenant-id" in _vary(resp)


async def test_subdomain_source_and_vary_host(probe, user_client):
    probe.state.tenants.settings.subdomain_base = "example.com"
    forget_hosts()
    async with user_client("a@x.io") as (a, _):
        t = await _create(a, "Acme")
    anon = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=probe), base_url=f"http://{t['slug']}.example.com"
    )
    async with anon:
        resp = await anon.get("/probe")
        assert resp.json() == {"tenant": t["id"], "source": "subdomain"}
        assert "host" in _vary(resp)


async def test_vary_has_no_duplicates(probe, user_client):
    async with user_client("a@x.io") as (a, _):
        await _create(a, "One")
        resp = await a.get("/probe", headers={"X-Tenant-ID": "nope"})
        tokens = _vary(resp)
        assert len(tokens) == len(set(tokens))


async def test_session_source_varies_on_cookie(probe, user_client):
    """The tenant came from the session cookie, so a shared cache must key on it (#418)."""
    async with user_client("a@x.io") as (a, _):
        await _create(a, "One")
        resp = await a.get("/probe")
        assert resp.json()["source"] == "session"
        assert "cookie" in _vary(resp)
