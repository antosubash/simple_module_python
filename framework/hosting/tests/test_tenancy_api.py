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


def _mount_probe(app, dep=None) -> None:
    """Mount a public ``GET /api/probe-tenant`` guarded by ``dep`` (``require_tenant()``)."""
    router = APIRouter(dependencies=[Depends(dep if dep is not None else require_tenant())])

    @router.get("/api/probe-tenant")
    async def probe() -> dict:
        return {"tenant": current_tenant_id.get()}

    app.include_router(router)
    app.state.public_routes.add_prefix("/api/probe-tenant", methods={"GET"})


async def test_multi_tenant_host_reports_multi(app):
    assert tenancy_mode(app) is TenancyMode.MULTI


async def test_single_host_reports_single_and_default_id(single_app):
    assert tenancy_mode(single_app) is TenancyMode.SINGLE
    assert single_tenant_id(single_app) == DEFAULT_TENANT_ID


async def test_pinned_single_host_reports_its_tenant(pinned_app):
    assert tenancy_mode(pinned_app) is TenancyMode.SINGLE
    assert single_tenant_id(pinned_app) == "main"


async def test_require_tenant_binds_single_tenant_without_middleware(single_app):
    _mount_probe(single_app)
    async with await _client(single_app) as c:
        assert (await c.get("/api/probe-tenant")).json() == {"tenant": DEFAULT_TENANT_ID}


async def test_require_tenant_403_when_multi_and_unresolved(app):
    _mount_probe(app)
    async with await _client(app) as c:
        resp = await c.get("/api/probe-tenant")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "tenant_required"


async def test_require_tenant_binds_the_resolved_tenant_when_multi(app, monkeypatch):
    async def resolver(_request: Request) -> str:
        return "acme"

    monkeypatch.setattr(app.state, "tenant_resolver", resolver, raising=False)
    _mount_probe(app)
    async with await _client(app) as c:
        resp = await c.get("/api/probe-tenant")
    assert resp.json() == {"tenant": "acme"}


async def test_require_tenant_custom_missing_response(app):
    dep = require_tenant(on_missing=lambda _r: HTTPException(404, "Page not found"))
    _mount_probe(app, dep)
    async with await _client(app) as c:
        assert (await c.get("/api/probe-tenant")).status_code == 404


async def _post_unflushed_note(app, *dependencies) -> list[tuple[str, str | None]]:
    """POST a row the endpoint only ``add``s, then read back what was committed.

    No flush in the endpoint: the row is stamped when the request's session
    commits (``CommitBeforeResponseMiddleware``), so the tenant ``require_tenant``
    bound has to still be bound at that point, not just inside the handler.
    """
    async with app.state.sm.db.engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    # Router-level dependencies run before the route's own get_db.
    router = APIRouter(dependencies=[*dependencies, Depends(require_tenant())])

    @router.post("/api/probe-notes")
    async def create_note(db=Depends(get_db)) -> dict:
        db.add(_Note(body="hello"))
        return {"bound": current_tenant_id.get()}

    app.include_router(router)
    app.state.public_routes.add_prefix("/api/probe-notes", methods={"POST"})
    async with await _client(app) as c:
        resp = await c.post("/api/probe-notes")
    assert resp.status_code == 200, resp.text

    # A fresh session proves the row was committed, not just added.
    async with app.state.sm.db.session_factory() as session:
        with all_tenants():
            rows = (await session.execute(select(_Note))).scalars().all()
    return [(r.body, r.tenant_id) for r in rows]


async def test_require_tenant_stamps_writes_single_host(single_app):
    """Review focus 2: a write after require_tenant() commits under the bound tenant."""
    assert await _post_unflushed_note(single_app) == [("hello", DEFAULT_TENANT_ID)]


async def test_require_tenant_binding_outlives_the_commit_in_strict_mode(app, monkeypatch):
    """Review focus 2, pinned: only require_tenant() binds, and strict mode is on.

    The resolver answers ``None``, so ``TenantMiddleware`` binds nothing; a
    dependency ahead of ``require_tenant()`` records ``acme`` on
    ``request.state`` the way the middleware would. If the binding were gone
    by the time the session commits, the strict-mode flush would raise instead
    of stamping ``acme``.
    """

    async def no_tenant(_request: Request) -> None:
        return None

    async def resolved_elsewhere(request: Request) -> None:
        request.state.tenant_id = "acme"

    monkeypatch.setattr(app.state, "tenant_resolver", no_tenant, raising=False)
    assert app.state.sm.db.tenant_strict
    rows = await _post_unflushed_note(app, Depends(resolved_elsewhere))
    assert rows == [("hello", "acme")]


async def test_tenant_vary_reads_what_the_middleware_recorded():
    request = Request({"type": "http", "headers": [], "state": {"tenant_vary": ("Host",)}})
    assert tenant_vary(request) == ("Host",)
    assert tenant_vary(Request({"type": "http", "headers": [], "state": {}})) == ()
