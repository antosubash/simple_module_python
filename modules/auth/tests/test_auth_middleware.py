"""Tests for the provider-agnostic AuthMiddleware."""

from __future__ import annotations

import httpx
import pytest
from auth.contracts.schemas import UserContext
from auth.middleware import AuthMiddleware
from auth.state import AuthState
from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse

SECRET = "test-middleware-secret"

_TEST_USER = UserContext(
    id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    email="test@example.com",
    name="Test User",
    roles=["admin"],
)


class _StubProvider:
    name = "stub"

    def __init__(self, *, user: UserContext | None = None):
        self._user = user

    async def resolve_user(self, request):
        return self._user

    def get_login_url(self, request, next_url=None):
        return "/stub/login"

    def get_logout_url(self, request):
        return "/stub/logout"

    def get_public_paths(self):
        return (("/stub/login", "/stub/public/"), ())

    def is_bearer_request(self, request):
        auth = request.headers.get("authorization", "")
        return auth.startswith("Bearer ")


def _build_app(provider, *, principal_resolvers=None, public_routes=None):
    app = FastAPI()
    app.state.auth = AuthState(
        auth_provider=provider,
        principal_resolvers=list(principal_resolvers or []),
    )
    if public_routes is not None:
        app.state.public_routes = public_routes

    async def _handler(request: Request, path: str = ""):
        user = getattr(request.state, "user", None)
        return JSONResponse(
            {
                "user": user.to_session_dict() if user else None,
            }
        )

    app.add_api_route("/{path:path}", _handler, methods=["GET", "POST", "PATCH"])

    app.add_middleware(AuthMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=SECRET)
    return app


@pytest.fixture
def authenticated_app():
    return _build_app(_StubProvider(user=_TEST_USER))


@pytest.fixture
def unauthenticated_app():
    return _build_app(_StubProvider(user=None))


async def test_authenticated_request_sets_user(authenticated_app):
    transport = httpx.ASGITransport(app=authenticated_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/some/page")
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "test@example.com"


async def test_unauthenticated_browser_redirects_to_login(unauthenticated_app):
    transport = httpx.ASGITransport(app=unauthenticated_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False
    ) as c:
        resp = await c.get("/protected/page")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/stub/login"


async def test_unauthenticated_api_returns_401(unauthenticated_app):
    transport = httpx.ASGITransport(app=unauthenticated_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/protected")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


async def test_unauthenticated_bearer_returns_401(unauthenticated_app):
    transport = httpx.ASGITransport(app=unauthenticated_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/some/page", headers={"Authorization": "Bearer bad"})
    assert resp.status_code == 401


async def test_public_paths_skip_auth(unauthenticated_app):
    transport = httpx.ASGITransport(app=unauthenticated_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/stub/login")
    assert resp.status_code == 200


async def test_framework_public_paths_skip_auth(unauthenticated_app):
    transport = httpx.ASGITransport(app=unauthenticated_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/health")
    assert resp.status_code == 200


async def test_root_is_public(unauthenticated_app):
    transport = httpx.ASGITransport(app=unauthenticated_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/")
    assert resp.status_code == 200


async def test_registry_public_route_skips_auth():
    """A module-contributed public route lets an unauthenticated GET through."""
    from simple_module_core.public_routes import PublicRouteRegistry

    registry = PublicRouteRegistry()
    registry.add_prefix("/api/gis/stac")
    app = _build_app(_StubProvider(user=None), public_routes=registry)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/gis/stac/collections")
    assert resp.status_code == 200
    assert resp.json()["user"] is None


async def test_registry_method_scoping_gates_other_verbs():
    """A GET-scoped public rule exempts GET but still gates PATCH on the same path."""
    from simple_module_core.public_routes import PublicRouteRegistry

    registry = PublicRouteRegistry()
    registry.add_regex(r"/api/gis/datasets/[^/]+/tilejson$", methods={"GET"})
    app = _build_app(_StubProvider(user=None), public_routes=registry)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        ok = await c.get("/api/gis/datasets/42/tilejson")
        gated = await c.patch("/api/gis/datasets/42/tilejson")
    assert ok.status_code == 200
    assert gated.status_code == 401


async def test_no_registry_falls_back_to_provider_paths(unauthenticated_app):
    """Apps built without a public-routes registry still honor provider paths."""
    transport = httpx.ASGITransport(app=unauthenticated_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        public = await c.get("/stub/public/data")
        gated = await c.get("/api/protected")
    assert public.status_code == 200
    assert gated.status_code == 401


async def test_resolver_chain_fallback():
    """When provider returns None, fall through to principal resolvers."""

    async def fake_resolver(request):
        auth = request.headers.get("authorization", "")
        if auth == "Bearer good-token":
            return _TEST_USER
        return None

    app = _build_app(_StubProvider(user=None), principal_resolvers=[fake_resolver])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/protected", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "test@example.com"


async def test_resolver_exception_is_logged_and_skipped():
    """A resolver that raises should be caught; middleware continues."""

    async def bad_resolver(request):
        raise RuntimeError("boom")

    app = _build_app(_StubProvider(user=None), principal_resolvers=[bad_resolver])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False
    ) as c:
        resp = await c.get("/protected/page")
    assert resp.status_code == 302


class TestDeepLinkPreservation:
    """AuthMiddleware stashes where an anonymous visitor was heading.

    The value is replayed into a ``Location`` header after login, so it is
    stored relative and sanitised on the way in — see
    ``simple_module_core.redirect_safety``.
    """

    async def _get(self, app, path: str):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as c:
            return await c.get(path)

    async def test_target_is_offered_to_the_provider(self):
        """The provider is handed the target, not left to guess it."""
        seen: list[str | None] = []

        class _RecordingProvider(_StubProvider):
            def get_login_url(self, request, next_url=None):
                seen.append(next_url)
                return "/stub/login"

        app = _build_app(_RecordingProvider())
        app.add_middleware(AuthMiddleware)
        app.add_middleware(SessionMiddleware, secret_key=SECRET)

        await self._get(app, "/protected/page?tab=2")

        assert seen == ["/protected/page?tab=2"]

    async def test_target_is_relative_not_absolute(self):
        """``str(request.url)`` would hand the provider an absolute URL —
        needless, and the wrong shape for a redirect target."""
        seen: list[str | None] = []

        class _RecordingProvider(_StubProvider):
            def get_login_url(self, request, next_url=None):
                seen.append(next_url)
                return "/stub/login"

        app = _build_app(_RecordingProvider())
        app.add_middleware(AuthMiddleware)
        app.add_middleware(SessionMiddleware, secret_key=SECRET)

        await self._get(app, "/protected/page")

        assert seen == ["/protected/page"]
        assert not seen[0].startswith("http")

    async def test_authenticated_request_stashes_nothing(self):
        """Only the anonymous branch records a target."""
        seen: list[str | None] = []

        class _RecordingProvider(_StubProvider):
            def get_login_url(self, request, next_url=None):
                seen.append(next_url)
                return "/stub/login"

        app = _build_app(_RecordingProvider(user=_TEST_USER))
        app.add_middleware(AuthMiddleware)
        app.add_middleware(SessionMiddleware, secret_key=SECRET)

        resp = await self._get(app, "/protected/page")

        assert resp.status_code == 200
        assert seen == []
