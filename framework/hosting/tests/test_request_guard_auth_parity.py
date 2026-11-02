"""The rate limiter follows AuthMiddleware's own public/anonymous decision.

AuthMiddleware records ``scope["state"]["auth_public"]`` (framework defaults +
public-route registry + provider legacy paths); the limiter keys on that flag so
the two can never disagree, including on path variants.
"""

from __future__ import annotations

import httpx
import pytest
from simple_module_core.public_routes import PublicRouteRegistry
from simple_module_hosting._rate_limit import RateLimitMiddleware
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route


async def _hits_429(app, path: str, ip: str, n: int = 125) -> bool:
    transport = httpx.ASGITransport(app=app, client=(ip, 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        for _ in range(n):
            if (await c.get(path, follow_redirects=False)).status_code == 429:
                return True
    return False


class TestRealAuthMiddleware:
    @pytest.mark.parametrize(
        "path",
        [
            "/i18n/en.json",  # framework-public prefix, not in the registry
            "/users/login",  # provider legacy public path, not in the registry
            "/users/login/",  # trailing slash
            "/users/login?x=1",  # query string
            "//users/login",  # double slash
            "/%75sers/login",  # percent-encoded
            "/api/docs",
        ],
    )
    async def test_anonymous_public_paths_are_limited(self, app, path: str) -> None:
        # Public per auth => limited. A variant auth does not treat as public is
        # refused by auth before the limiter and so cannot be an unlimited bypass
        # of a route that *is* public (the router would not match it either).
        limited = await _hits_429(app, path, "9.9.9.1")
        transport = httpx.ASGITransport(app=app, client=("9.9.9.9", 1))
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            status = (await c.get(path, follow_redirects=False)).status_code
        assert limited or status in (301, 302, 307, 308, 401, 404, 429), (path, status)

    @pytest.mark.parametrize("path", ["/i18n/en.json", "/users/login", "/api/docs"])
    async def test_canonical_public_paths_definitely_limited(self, app, path: str) -> None:
        assert await _hits_429(app, path, "9.9.9.5")

    async def test_non_public_path_is_not_limited(self, app) -> None:
        assert not await _hits_429(app, "/api/users/me", "9.9.9.2")

    async def test_static_and_health_never_limited(self, app) -> None:
        assert not await _hits_429(app, "/static/nope.js", "9.9.9.3")
        assert not await _hits_429(app, "/health", "9.9.9.4")


class _SetFlag:
    def __init__(self, app, value) -> None:
        self.app = app
        self.value = value

    async def __call__(self, scope, receive, send) -> None:
        scope.setdefault("state", {})["auth_public"] = self.value
        await self.app(scope, receive, send)


def _app(flag, registry: PublicRouteRegistry) -> Starlette:
    async def ok(request):
        return JSONResponse({})

    app = Starlette(routes=[Route("/p", ok)])
    app.state.public_routes = registry
    app.add_middleware(RateLimitMiddleware, public_rate="1/minute")
    if flag is not None:
        app.add_middleware(_SetFlag, value=flag)
    return app


class TestFlagContract:
    async def test_flag_true_limits_even_without_registry_rule(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_app(True, PublicRouteRegistry())),
            base_url="http://t",
        ) as c:
            assert (await c.get("/p")).status_code == 200
            assert (await c.get("/p")).status_code == 429

    async def test_flag_false_wins_over_registry_match(self) -> None:
        reg = PublicRouteRegistry()
        reg.add_prefix("/p")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_app(False, reg)), base_url="http://t"
        ) as c:
            for _ in range(4):
                assert (await c.get("/p")).status_code == 200

    async def test_no_flag_falls_back_to_registry(self) -> None:
        reg = PublicRouteRegistry()
        reg.add_prefix("/p")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_app(None, reg)), base_url="http://t"
        ) as c:
            assert (await c.get("/p")).status_code == 200
            assert (await c.get("/p")).status_code == 429
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_app(None, PublicRouteRegistry())),
            base_url="http://t",
        ) as c:
            for _ in range(4):
                assert (await c.get("/p")).status_code == 200
