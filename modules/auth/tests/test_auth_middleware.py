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


def _build_app(provider, *, principal_resolvers=None):
    app = FastAPI()
    app.state.auth = AuthState(
        auth_provider=provider,
        principal_resolvers=list(principal_resolvers or []),
    )

    @app.get("/{path:path}")
    async def catch_all(request: Request, path: str = ""):
        user = getattr(request.state, "user", None)
        return JSONResponse(
            {
                "user": user.to_session_dict() if user else None,
            }
        )

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
