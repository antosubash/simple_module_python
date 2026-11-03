"""Operational paths are matched exactly or at slash boundaries."""

from types import SimpleNamespace

import httpx
import pytest
from simple_module_hosting._rate_limit import RateLimitMiddleware
from simple_module_hosting.maintenance import MaintenanceMiddleware
from simple_module_hosting.path_matching import matches_path
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/healthcare/x", 503),
        ("/healthX", 503),
        ("/api/docsearch", 503),
        ("/api/docsX", 503),
        ("/health", 200),
        ("/health/ready", 200),
    ],
)
async def test_maintenance_operational_path_boundaries(path, expected):
    async def ok(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route(path, ok)])
    app.state.host = SimpleNamespace(settings=SimpleNamespace(maintenance_mode=True))
    app.add_middleware(MaintenanceMiddleware)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.get(path, headers={"Accept": "application/json"})
        ).status_code == expected


@pytest.mark.parametrize(
    "path,limited",
    [
        ("/healthcare/x", True),
        ("/healthX", True),
        ("/api/docsearch", True),
        ("/api/docsX", True),
        ("/api/docs", True),
        ("/health", False),
        ("/health/ready", False),
    ],
)
async def test_anonymous_rate_limit_operational_path_boundaries(path, limited):
    async def ok(request):
        return PlainTextResponse("ok")

    class PublicTraffic:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            scope.setdefault("state", {})["auth_public"] = True
            await self.app(scope, receive, send)

    app = Starlette(routes=[Route(path, ok)])
    app.add_middleware(RateLimitMiddleware, public_rate="1/minute")
    app.add_middleware(PublicTraffic)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get(path)).status_code == 200
        assert (await client.get(path)).status_code == (429 if limited else 200)


def test_path_matcher_requires_slash_terminated_prefixes():
    with pytest.raises(ValueError):
        matches_path("/healthcare", prefixes=("/health",))
