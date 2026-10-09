"""simple_module_hosting.tenancy — the tenancy facts modules used to reverse-engineer (#418)."""

from __future__ import annotations

import httpx
import pytest
from fastapi import APIRouter, Depends, HTTPException, Request
from simple_module_db import DEFAULT_TENANT_ID, all_tenants, current_tenant_id
from simple_module_db.base import create_module_base
from simple_module_db.deps import get_db
from simple_module_db.mixins import MultiTenantMixin
from simple_module_hosting.tenancy import (
    TenancyMode,
    require_tenant,
    single_tenant_id,
    tenancy_mode,
    tenant_vary,
)
from simple_module_test.fixtures import _build_app
from sqlmodel import Field, select

_Base = create_module_base("tenancy_api_test")


class _Note(_Base, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "tenancy_api_test_note"
    id: int | None = Field(default=None, primary_key=True)
    body: str = Field(max_length=100)


@pytest.fixture
async def single_app(settings):
    single = settings.model_copy(update={"multi_tenant": False, "default_tenant": ""})
    async for application in _build_app(single, seed_admin=True):
        yield application


@pytest.fixture
async def pinned_app(settings):
    pinned = settings.model_copy(update={"multi_tenant": False, "default_tenant": "main"})
    async for application in _build_app(pinned, seed_admin=True):
        yield application


async def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_multi_tenant_host_reports_multi(app):
    assert tenancy_mode(app) is TenancyMode.MULTI


async def test_single_host_reports_single_and_default_id(single_app):
    assert tenancy_mode(single_app) is TenancyMode.SINGLE
    assert single_tenant_id(single_app) == DEFAULT_TENANT_ID


async def test_pinned_single_host_reports_its_tenant(pinned_app):
    assert tenancy_mode(pinned_app) is TenancyMode.SINGLE
    assert single_tenant_id(pinned_app) == "main"


async def test_require_tenant_binds_single_tenant_without_middleware(single_app):
    router = APIRouter(dependencies=[Depends(require_tenant())])

    @router.get("/api/probe-tenant")
    async def probe() -> dict:
        return {"tenant": current_tenant_id.get()}

    single_app.include_router(router)
    single_app.state.public_routes.add_prefix("/api/probe-tenant", methods={"GET"})
    async with await _client(single_app) as c:
        assert (await c.get("/api/probe-tenant")).json() == {"tenant": DEFAULT_TENANT_ID}


async def test_require_tenant_403_when_multi_and_unresolved(app):
    router = APIRouter(dependencies=[Depends(require_tenant())])

    @router.get("/api/probe-tenant")
    async def probe() -> dict:
        return {}

    app.include_router(router)
    app.state.public_routes.add_prefix("/api/probe-tenant", methods={"GET"})
    async with await _client(app) as c:
        resp = await c.get("/api/probe-tenant")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "tenant_required"


async def test_require_tenant_binds_the_resolved_tenant_when_multi(app, monkeypatch):
    async def resolver(_request: Request) -> str:
        return "acme"

    monkeypatch.setattr(app.state, "tenant_resolver", resolver, raising=False)
    router = APIRouter(dependencies=[Depends(require_tenant())])

    @router.get("/api/probe-tenant")
    async def probe() -> dict:
        return {"tenant": current_tenant_id.get()}

    app.include_router(router)
    app.state.public_routes.add_prefix("/api/probe-tenant", methods={"GET"})
    async with await _client(app) as c:
        resp = await c.get("/api/probe-tenant")
    assert resp.json() == {"tenant": "acme"}


async def test_require_tenant_custom_missing_response(app):
    dep = require_tenant(on_missing=lambda _r: HTTPException(404, "Page not found"))
    router = APIRouter(dependencies=[Depends(dep)])

    @router.get("/api/probe-tenant")
    async def probe() -> dict:
        return {}

    app.include_router(router)
    app.state.public_routes.add_prefix("/api/probe-tenant", methods={"GET"})
    async with await _client(app) as c:
        assert (await c.get("/api/probe-tenant")).status_code == 404


async def test_require_tenant_stamps_writes_single_host(single_app):
    """Review focus 2: a write after require_tenant() commits under the bound tenant."""
    async with single_app.state.sm.db.engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    # Router-level dependency: require_tenant() is entered before the route's
    # get_db, so it exits after it — the commit runs while the tenant is bound.
    router = APIRouter(dependencies=[Depends(require_tenant())])

    @router.post("/api/probe-notes")
    async def create_note(db=Depends(get_db)) -> dict:
        note = _Note(body="hello")
        db.add(note)
        await db.flush()
        return {"id": note.id, "bound": current_tenant_id.get()}

    single_app.include_router(router)
    single_app.state.public_routes.add_prefix("/api/probe-notes", methods={"POST"})
    async with await _client(single_app) as c:
        resp = await c.post("/api/probe-notes")
    assert resp.status_code == 200, resp.text
    assert resp.json()["bound"] == DEFAULT_TENANT_ID

    # A fresh session proves the row was committed, not just flushed.
    async with single_app.state.sm.db.session_factory() as session:
        with all_tenants():
            rows = (await session.execute(select(_Note))).scalars().all()
    assert [(r.body, r.tenant_id) for r in rows] == [("hello", DEFAULT_TENANT_ID)]


async def test_tenant_vary_reads_what_the_middleware_recorded():
    request = Request({"type": "http", "headers": [], "state": {"tenant_vary": ("Host",)}})
    assert tenant_vary(request) == ("Host",)
    assert tenant_vary(Request({"type": "http", "headers": [], "state": {}})) == ()
