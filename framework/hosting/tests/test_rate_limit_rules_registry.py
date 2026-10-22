"""Per-route rate-limit rules and the ``RateLimit`` dependency (#529)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
from fastapi import APIRouter, Depends, FastAPI
from simple_module_core.public_routes import PublicRouteRegistry
from simple_module_core.rate_limit import (
    InProcessWindowStore,
    RateKey,
    RateLimitRegistry,
    RateLimitRule,
)
from simple_module_hosting._rate_limit import RateLimitMiddleware
from simple_module_hosting.rate_limit_deps import RateLimit
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

_USER_HEADER = b"x-user"
_TENANT_HEADER = b"x-tenant"
_RATE = "10/minute"


class _Ident:
    """Stand-in for Auth + Tenant middleware: identity comes from headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope["headers"])
            state = scope.setdefault("state", {})
            if _USER_HEADER in headers:
                state["user"] = SimpleNamespace(id=headers[_USER_HEADER].decode())
            if _TENANT_HEADER in headers:
                state["tenant_id"] = headers[_TENANT_HEADER].decode()
        await self.app(scope, receive, send)


def _app(registry: RateLimitRegistry) -> Starlette:
    async def ok(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/api/things", ok, methods=["GET", "POST"])])
    app.state.rate_limit_rules = registry
    app.add_middleware(RateLimitMiddleware, public_rate=None)
    app.add_middleware(_Ident)
    return app


def _client(app: ASGIApp) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=("9.9.9.9", 1))
    return httpx.AsyncClient(transport=transport, base_url="http://t")


def _registry(rule: RateLimitRule) -> RateLimitRegistry:
    reg = RateLimitRegistry()
    reg.add_prefix("/api/things", rule)
    return reg


async def _burst(c: httpx.AsyncClient, user: str | None, n: int, method: str = "POST") -> list[int]:
    headers = {_USER_HEADER.decode(): user} if user else {}
    return [(await c.request(method, "/api/things", headers=headers)).status_code for _ in range(n)]


async def test_two_users_on_one_ip_each_get_their_own_budget() -> None:
    reg = _registry(RateLimitRule(_RATE, key="user", methods=frozenset({"POST"})))
    async with _client(_app(reg)) as c:
        alice = await _burst(c, "alice", 11)
        bob = await _burst(c, "bob", 10)
        r = await c.post("/api/things", headers={_USER_HEADER.decode(): "alice"})
        get = await c.get("/api/things", headers={_USER_HEADER.decode(): "alice"})
    assert alice[:10] == [200] * 10 and alice[10] == 429
    assert bob == [200] * 10
    assert r.status_code == 429 and 1 <= int(r.headers["retry-after"]) <= 60
    assert get.status_code == 200, "a POST-only rule must not limit GET"


async def test_anonymous_falls_back_to_ip() -> None:
    reg = _registry(RateLimitRule(_RATE, key="user"))
    async with _client(_app(reg)) as c:
        codes = await _burst(c, None, 11)
        signed_in = await _burst(c, "carol", 1)
    assert codes[-1] == 429 and codes[:10] == [200] * 10
    assert signed_in == [200]


async def test_ip_key_shares_one_budget_across_users() -> None:
    reg = _registry(RateLimitRule("2/minute", key="ip"))
    async with _client(_app(reg)) as c:
        assert await _burst(c, "a", 2) == [200, 200]
        assert await _burst(c, "b", 1) == [429]


async def test_tenant_key_pools_users_of_a_tenant_and_falls_back() -> None:
    reg = _registry(RateLimitRule("2/minute", key="tenant"))
    async with _client(_app(reg)) as c:

        async def hit(user: str, tenant: str | None) -> int:
            h = {_USER_HEADER.decode(): user}
            if tenant:
                h[_TENANT_HEADER.decode()] = tenant
            return (await c.post("/api/things", headers=h)).status_code

        assert [await hit("a", "t1"), await hit("b", "t1"), await hit("c", "t1")] == [
            200,
            200,
            429,
        ]
        assert await hit("a", "t2") == 200
        # No tenant resolved: falls back to the IP bucket, not a shared "None" tenant.
        assert [await hit("a", None), await hit("b", None), await hit("c", None)] == [
            200,
            200,
            429,
        ]


async def test_anonymous_tenant_traffic_is_counted_per_ip_not_per_tenant() -> None:
    # One anonymous client must not be able to drain a tenant's shared budget.
    reg = _registry(RateLimitRule("1/minute", key="tenant"))
    async with _client(_app(reg)) as c:
        h = {_TENANT_HEADER.decode(): "t1"}
        assert (await c.post("/api/things", headers=h)).status_code == 200
        assert (await c.post("/api/things", headers=h)).status_code == 429
        member = {**h, _USER_HEADER.decode(): "a"}
        assert (await c.post("/api/things", headers=member)).status_code == 200


async def test_rule_precedes_the_public_tier() -> None:
    reg = _registry(RateLimitRule("1/minute", key="ip"))
    async with _client(_app(reg)) as c:
        assert await _burst(c, None, 2, "GET") == [200, 429]


def _dep_app(key: RateKey) -> FastAPI:
    app = FastAPI()
    app.state.sm = SimpleNamespace(rate_limit_store=InProcessWindowStore())

    @app.post("/dep", dependencies=[Depends(RateLimit("3/minute", key=key))])
    async def dep() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(_Ident)
    return app


async def test_dependency_limits_per_user_with_retry_after() -> None:
    async with _client(_dep_app("user")) as c:
        h = {_USER_HEADER.decode(): "alice"}
        codes = [(await c.post("/dep", headers=h)).status_code for _ in range(3)]
        over = await c.post("/dep", headers=h)
        other = await c.post("/dep", headers={_USER_HEADER.decode(): "bob"})
    assert codes == [200] * 3
    assert over.status_code == 429 and int(over.headers["retry-after"]) >= 1
    assert other.status_code == 200


async def test_public_rate_and_registry_rule_on_one_path_count_separately() -> None:
    # Same kind/pattern/methods: each request must bump each counter once.
    reg = RateLimitRegistry()
    reg.add_exact("/api/things", RateLimitRule("2/minute", key="ip"))
    app = _app(reg)
    public = PublicRouteRegistry()
    public.add_exact("/api/things", rate="2/minute")
    app.state.public_routes = public
    async with _client(app) as c:
        assert await _burst(c, None, 3, "GET") == [200, 200, 429]


async def test_dependency_budget_is_per_include_prefix() -> None:
    app = FastAPI()
    app.state.sm = SimpleNamespace(rate_limit_store=InProcessWindowStore())
    router = APIRouter()

    @router.post("/dep", dependencies=[Depends(RateLimit("1/minute", key="ip"))])
    async def dep() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router, prefix="/a")
    app.include_router(router, prefix="/b")
    async with _client(app) as c:
        assert (await c.post("/a/dep")).status_code == 200
        assert (await c.post("/b/dep")).status_code == 200
        assert (await c.post("/a/dep")).status_code == 429
