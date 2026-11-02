"""Per-tenant branding resolution only runs where a page renders, once per miss.

Shared-props providers run on every request. Resolving a tenant's branding for
an API call or a static file is a cache lookup — or a DB read on a miss — for a
prop nobody reads; and N concurrent misses for one tenant must share one read.
"""

from __future__ import annotations

import asyncio

import pytest
from branding import tenant_branding
from branding.shared_props import renders_a_page
from starlette.requests import Request


@pytest.fixture(autouse=True)
def _fresh_cache(app):
    tenant_branding.forget(app)
    yield
    tenant_branding.forget(app)


def _request(path: str, **headers: str) -> Request:
    raw = [(k.lower().replace("_", "-").encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "GET", "path": path, "headers": raw})


@pytest.mark.parametrize(
    ("path", "headers", "expected"),
    [
        ("/tenants/", {"X-Inertia": "true", "Accept": "application/json"}, True),
        ("/tenants/", {"Accept": "text/html,application/xhtml+xml"}, True),
        ("/tenants/", {"Accept": "*/*"}, True),
        ("/tenants/", {}, True),
        ("/tenants/", {"Accept": "application/json"}, False),
        ("/api/tenants/", {"Accept": "*/*"}, False),
        ("/api/branding/logo", {"Accept": "image/webp,*/*"}, False),
        ("/static/dist/app.js", {"Accept": "*/*"}, False),
    ],
)
def test_which_requests_render_a_page(path, headers, expected):
    assert renders_a_page(_request(path, **headers)) is expected


async def test_api_requests_never_read_tenant_overrides(tenant_client, monkeypatch):
    reads: list[str] = []
    original = tenant_branding.read_overrides

    async def counting(app, tenant_id):
        reads.append(tenant_id)
        return await original(app, tenant_id)

    monkeypatch.setattr(tenant_branding, "read_overrides", counting)
    async with tenant_client() as a:
        assert (await a.client.get("/api/tenants/")).status_code == 200
        assert reads == []
        page = await a.client.get("/tenants/", headers={"X-Inertia": "true"})
        assert page.json()["props"]["branding"]["appName"]
        assert reads == [a.tenant_id]


async def test_concurrent_misses_share_one_read(app, monkeypatch):
    reads = 0
    release = asyncio.Event()

    async def slow(_app, _tenant_id):
        nonlocal reads
        reads += 1
        await release.wait()
        return {"app_name": "Acme"}

    monkeypatch.setattr(tenant_branding, "read_overrides", slow)
    waiters = [asyncio.create_task(tenant_branding.resolve_for(app, "acme")) for _ in range(5)]
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*waiters)

    assert reads == 1
    assert {r.settings.app_name for r in results} == {"Acme"}


async def test_a_miss_after_a_forget_does_not_join_the_older_read(app, monkeypatch):
    reads: list[str] = []
    release = asyncio.Event()

    async def slow(_app, _tenant_id):
        reads.append("read")
        await release.wait()
        return {"app_name": f"v{len(reads)}"}

    monkeypatch.setattr(tenant_branding, "read_overrides", slow)
    first = asyncio.create_task(tenant_branding.resolve_for(app, "acme"))
    await asyncio.sleep(0)
    tenant_branding.forget(app, "acme")  # the row changed while the read was in flight
    second = asyncio.create_task(tenant_branding.resolve_for(app, "acme"))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)

    assert len(reads) == 2
    # Only the post-change read is cached.
    assert (await tenant_branding.resolve_for(app, "acme")).settings.app_name == "v2"
