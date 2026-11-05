"""Unknown hosts expire quickly and committed tenant creation invalidates only its slug."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from cachetools import TTLCache
from fastapi import FastAPI
from simple_module_core.invalidation import Invalidation
from simple_module_core.singleflight import MAX_FILL_ATTEMPTS
from simple_module_db.transaction import finalize_session
from tenants import host_resolver, resolver
from tenants.constants import INVALIDATION_CHANNEL
from tenants.contracts.schemas import TenantCreate
from tenants.service import TenantService


def _fake_app(db) -> FastAPI:
    @asynccontextmanager
    async def session():
        yield db

    app = FastAPI()
    app.state.sm = SimpleNamespace(db=SimpleNamespace(session_factory=session))
    return app


async def test_unknown_slug_is_cached_until_expiry_or_invalidation(monkeypatch):
    now = [0]
    monkeypatch.setattr(
        host_resolver, "_MISSING_SLUGS", TTLCache(maxsize=10_000, ttl=5, timer=lambda: now[0])
    )
    reads = 0

    class DB:
        async def execute(self, stmt):
            nonlocal reads
            reads += 1
            return SimpleNamespace(first=lambda: None)

    app = _fake_app(DB())
    for _ in range(50):
        assert await host_resolver.tenant_for_slug(app, "missing") is None
    assert reads == 1
    now[0] = 6
    await host_resolver.tenant_for_slug(app, "missing")
    assert reads == 2
    host_resolver.forget_hosts()
    await host_resolver.tenant_for_slug(app, "missing")
    assert reads == 3


async def test_previously_missing_slug_resolves_right_after_create(app, user_client):
    assert await host_resolver.tenant_for_slug(app, "new-org") is None
    async with user_client("new-owner@x.io") as (client, _):
        response = await client.post("/api/tenants/", json={"name": "New", "slug": "new-org"})
        assert response.status_code == 201
    hit = await host_resolver.tenant_for_slug(app, "new-org")
    assert hit is not None and hit[0] == response.json()["id"]


async def test_create_drops_the_missing_slug_only_after_commit(app, user_client):
    async with user_client("owner@x.io") as (_, owner_id):
        async with app.state.sm.db.session_factory() as db:
            service = TenantService(db, invalidate=resolver.make_invalidator(app))
            assert await host_resolver.tenant_for_slug(app, "fresh") is None
            tenant = await service.create_tenant(
                TenantCreate(name="Fresh", slug="fresh"), owner_user_id=owner_id
            )
            assert await host_resolver.tenant_for_slug(app, "fresh") is None
            await finalize_session(db)
        hit = await host_resolver.tenant_for_slug(app, "fresh")
        assert hit is not None and hit[0] == tenant.id


async def test_create_keeps_other_users_memberships_and_slugs(app, tenant_client, user_client):
    async with tenant_client("owner") as (_, tenant_id, bystander_id):
        bystander = await resolver.memberships_for(app, bystander_id)
        existing = bystander[0].slug
        cached_host = await host_resolver.tenant_for_slug(app, existing)
        assert cached_host is not None and cached_host[0] == tenant_id
        async with user_client("creator@x.io") as (client, _):
            response = await client.post("/api/tenants/", json={"name": "Other", "slug": "other"})
            assert response.status_code == 201
        assert resolver.cached_memberships(bystander_id) is bystander
        assert host_resolver._BY_SLUG.get(existing) == cached_host


def test_host_key_from_the_bus_drops_one_slug_and_no_memberships():
    resolver._MEMBERSHIPS["someone"] = []
    host_resolver._BY_SLUG["kept"] = ("kept-id", "active")
    host_resolver._MISSING_SLUGS["created"] = True
    key = host_resolver.host_invalidation_key("created")
    resolver._apply_invalidation(Invalidation(INVALIDATION_CHANNEL, key=key))
    assert "created" not in host_resolver._MISSING_SLUGS
    assert host_resolver._BY_SLUG.get("kept") == ("kept-id", "active")
    assert resolver.cached_memberships("someone") == []


async def test_host_invalidation_during_read_retries_before_caching():
    started, release = asyncio.Event(), asyncio.Event()
    reads = 0

    class DB:
        async def execute(self, stmt):
            nonlocal reads
            reads += 1
            row = None if reads == 1 else ("new-tenant", "active")
            started.set()
            await release.wait()
            return SimpleNamespace(first=lambda: row)

    app = _fake_app(DB())
    task = asyncio.create_task(host_resolver.tenant_for_slug(app, "racing"))
    await started.wait()
    host_resolver.forget_slug("racing")
    release.set()
    assert await task == ("new-tenant", "active")
    assert await host_resolver.tenant_for_slug(app, "racing") == ("new-tenant", "active")
    assert reads == 2


async def test_host_lookup_stops_retrying_under_continuous_invalidation():
    reads = 0

    class DB:
        async def execute(self, stmt):
            nonlocal reads
            reads += 1
            host_resolver.forget_slug("elsewhere")  # every read races an invalidation
            row = (f"read-{reads}", "active")
            return SimpleNamespace(first=lambda: row)

    app = _fake_app(DB())
    assert await host_resolver.tenant_for_slug(app, "busy") == (
        f"read-{MAX_FILL_ATTEMPTS}",
        "active",
    )
    assert reads == MAX_FILL_ATTEMPTS
    assert "busy" not in host_resolver._BY_SLUG
    assert "busy" not in host_resolver._MISSING_SLUGS
