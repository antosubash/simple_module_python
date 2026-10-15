"""``token_guard`` pass 4: include-level gates, and "anonymous" means no tenant either.

N1: FastAPI keeps ``include_router(..., dependencies=[...])`` out of the
original route's ``dependant``; the guard reads the effective route so an
include-level permission gate admits a token (capped by the gate), instead of
failing closed. N4: a token demoted to anonymous on a public route must not
keep the tenant context it pinned.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, Depends, FastAPI, Request
from simple_module_db import current_tenant_id
from simple_module_hosting._tenant import TenantMiddleware, TenantResolution
from simple_module_hosting.permissions import RequiresPermission
from simple_module_hosting.token_guard import token_route_guard


@dataclass
class _Principal:
    id: str = "u1"
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    scopes: list[str] | None = None
    required_permission: str | None = None


async def _get(app: FastAPI, path: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        return await client.get(path)


def _with_auth(app: FastAPI, principal: _Principal | None, *, public: bool = False) -> FastAPI:
    @app.middleware("http")
    async def fake_auth(request: Request, call_next):
        request.state.user = principal
        request.scope.setdefault("state", {})["auth_public"] = public
        return await call_next(request)

    return app


def _include_gated_app(principal: _Principal) -> FastAPI:
    app = FastAPI(dependencies=[Depends(token_route_guard)])
    app.state.sm = None
    sub = APIRouter()

    @sub.get("/x")
    async def x() -> dict:
        return {"ok": True}

    outer = APIRouter(prefix="/api")
    outer.include_router(sub, dependencies=[Depends(RequiresPermission("x.view"))])
    app.include_router(outer)
    return _with_auth(app, principal)


async def test_an_include_level_permission_gate_admits_a_scoped_token():
    app = _include_gated_app(_Principal(scopes=["x.view"], permissions=["x.view"]))
    assert (await _get(app, "/api/x")).status_code == 200


async def test_an_include_level_gate_still_caps_the_token():
    app = _include_gated_app(_Principal(scopes=["y.view"], permissions=["x.view"]))
    assert (await _get(app, "/api/x")).status_code == 403


async def test_a_principal_missing_its_required_permission_is_unauthenticated():
    app = _include_gated_app(
        _Principal(scopes=["x.view"], permissions=["x.view"], required_permission="t.use")
    )
    assert (await _get(app, "/api/x")).status_code == 401
    held = _Principal(
        scopes=["x.view"], permissions=["x.view", "t.use"], required_permission="t.use"
    )
    assert (await _get(_include_gated_app(held), "/api/x")).status_code == 200


def _tenant_app(principal: _Principal) -> FastAPI:
    app = FastAPI(dependencies=[Depends(token_route_guard)])
    app.state.sm = None

    async def resolver(request: Request) -> TenantResolution:
        user = getattr(request.state, "user", None)
        if user is not None:
            return TenantResolution("t-token", "token", ("Authorization",))
        return TenantResolution(None, None, ("Host",))

    app.state.tenant_resolver = resolver

    @app.get("/public")
    async def public(request: Request) -> dict:
        return {
            "user": getattr(request.state.user, "id", None),
            "ctx": current_tenant_id.get(),
            "state": request.state.tenant_id,
        }

    app.add_middleware(TenantMiddleware)
    return _with_auth(app, principal, public=True)


async def test_a_token_demoted_on_a_public_route_loses_its_pinned_tenant():
    resp = await _get(_tenant_app(_Principal(scopes=["x.view"])), "/public")
    assert resp.status_code == 200
    assert resp.json() == {"user": None, "ctx": None, "state": None}
    # Both answers' inputs stay in Vary.
    vary = {v.strip() for v in resp.headers["vary"].split(",")}
    assert {"Authorization", "Host"} <= vary


async def test_a_session_on_a_public_route_keeps_its_tenant():
    resp = await _get(_tenant_app(_Principal(scopes=None)), "/public")
    assert resp.json() == {"user": "u1", "ctx": "t-token", "state": "t-token"}
