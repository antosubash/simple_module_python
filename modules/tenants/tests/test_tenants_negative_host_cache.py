"""Unknown hosts expire quickly and committed tenant changes invalidate misses."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

from cachetools import TTLCache
from fastapi import FastAPI
from tenants import host_resolver


async def test_unknown_slug_is_cached_until_expiry_or_invalidation(monkeypatch):
    now = [0]
    monkeypatch.setattr(
        host_resolver,
        "_MISSING_SLUGS",
        TTLCache(maxsize=10_000, ttl=5, timer=lambda: now[0]),
        raising=False,
    )
    reads = 0

    class DB:
        async def execute(self, stmt):
            nonlocal reads
            reads += 1
            return SimpleNamespace(first=lambda: None)

    @asynccontextmanager
    async def session():
        yield DB()

    app = FastAPI()
    app.state.sm = SimpleNamespace(db=SimpleNamespace(session_factory=session))
    for _ in range(50):
        assert await host_resolver.tenant_for_slug(app, "missing") is None
    assert reads == 1
    now[0] = 6
    await host_resolver.tenant_for_slug(app, "missing")
    assert reads == 2
    host_resolver.forget_hosts()
    await host_resolver.tenant_for_slug(app, "missing")
    assert reads == 3


async def test_create_invalidates_negative_host_cache_after_commit(app, user_client):
    assert await host_resolver.tenant_for_slug(app, "new-org") is None
    async with user_client("new-owner@x.io") as (client, _):
        response = await client.post("/api/tenants/", json={"name": "New", "slug": "new-org"})
        assert response.status_code == 201
    assert (await host_resolver.tenant_for_slug(app, "new-org"))[0] == response.json()["id"]


async def test_rename_invalidates_old_hit_and_new_miss_only_after_commit(app, tenant_client):
    from simple_module_db.transaction import finalize_session
    from tenants.contracts.schemas import TenantCreate
    from tenants.resolver import make_invalidator
    from tenants.service import TenantService

    async with tenant_client("owner") as (_, tenant_id, _):
        async with app.state.sm.db.session_factory() as db:
            service = TenantService(db, invalidate=make_invalidator(app))
            tenant = await service.get(tenant_id)
            old_slug = tenant.slug
            assert (await host_resolver.tenant_for_slug(app, old_slug))[0] == tenant_id
            assert await host_resolver.tenant_for_slug(app, "renamed") is None
            await service.rename_tenant(tenant_id, TenantCreate(name="Renamed", slug="renamed"))
            assert await host_resolver.tenant_for_slug(app, "renamed") is None
            await finalize_session(db)
        assert await host_resolver.tenant_for_slug(app, old_slug) is None
        assert (await host_resolver.tenant_for_slug(app, "renamed"))[0] == tenant_id


async def test_host_invalidation_during_read_retries_before_caching():
    import asyncio

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

    @asynccontextmanager
    async def session():
        yield DB()

    app = FastAPI()
    app.state.sm = SimpleNamespace(db=SimpleNamespace(session_factory=session))
    task = asyncio.create_task(host_resolver.tenant_for_slug(app, "racing"))
    await started.wait()
    host_resolver.forget_hosts()
    release.set()
    assert await task == ("new-tenant", "active")
    assert await host_resolver.tenant_for_slug(app, "racing") == ("new-tenant", "active")
    assert reads == 2


async def test_rename_rollback_and_duplicate_slug_preserve_tenant(app, tenant_client):
    import pytest
    from tenants.contracts.schemas import TenantCreate
    from tenants.errors import TenantError
    from tenants.models import Tenant
    from tenants.resolver import make_invalidator
    from tenants.service import TenantService

    async with (
        tenant_client("owner") as (_, tenant_id, _),
        app.state.sm.db.session_factory() as db,
    ):
        original = await db.get(Tenant, tenant_id)
        original_name, original_slug = original.name, original.slug
        db.add(Tenant(name="Taken", slug="taken"))
        await db.commit()
        service = TenantService(db, invalidate=make_invalidator(app))
        renamed = await service.rename_tenant(tenant_id, TenantCreate(name="Name only"))
        assert (renamed.name, renamed.slug) == ("Name only", original_slug)
        await db.rollback()
        with pytest.raises(TenantError) as error:
            await service.rename_tenant(tenant_id, TenantCreate(name="Conflict", slug="taken"))
        assert error.value.status_code == 409
        await db.rollback()
        tenant = await service.get(tenant_id)
        assert (tenant.name, tenant.slug) == (original_name, original_slug)
