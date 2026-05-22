"""AuthMiddleware tests for the principal-resolver chain.

Covers ``app.state.auth.principal_resolvers`` consultation order, error
isolation, the session-short-circuit precedence, and the /api/* vs view-path
unauthenticated split (401 JSON vs 302 redirect).

Helpers + fixtures live in ``_middleware_support`` alongside the broader
middleware tests in ``test_users_middleware`` and the PUBLIC_PATHS suite in
``test_users_middleware_public_paths``.
"""

from __future__ import annotations

import httpx
import pytest
from _middleware_support import _build_app, _session_cookie
from fastapi import Request
from starlette.responses import JSONResponse


def _ctx(uid: str = "11111111-1111-1111-1111-111111111111", **overrides):
    """Build a UserContext for resolver tests."""
    from auth.contracts.schemas import UserContext

    fields = {
        "id": uid,
        "email": "pat@example.com",
        "name": "PAT User",
        "roles": ["user"],
        "tenant_id": None,
    }
    fields.update(overrides)
    return UserContext(**fields)


@pytest.mark.anyio
async def test_resolver_returning_context_authenticates_request(db_state):
    """A registered resolver that returns a UserContext authenticates the request."""

    async def stub_resolver(request):
        return _ctx()

    app = await _build_app(db_state, principal_resolvers=[stub_resolver])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard")

    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["email"] == "pat@example.com"


@pytest.mark.anyio
async def test_resolver_first_non_none_wins(db_state):
    """The first resolver returning a context wins; later resolvers are not consulted."""
    second_called = False

    async def first_none(request):
        return None

    async def second_returns(request):
        nonlocal second_called
        second_called = True
        return _ctx(email="second@example.com")

    async def third_should_not_run(request):
        raise AssertionError("third resolver should not run after a match")

    app = await _build_app(
        db_state,
        principal_resolvers=[first_none, second_returns, third_should_not_run],
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard")

    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "second@example.com"
    assert second_called


@pytest.mark.anyio
async def test_all_resolvers_return_none_falls_through_to_redirect(db_state):
    """When every resolver returns None for a view route → 302 to /users/login."""

    async def none_resolver(request):
        return None

    app = await _build_app(db_state, principal_resolvers=[none_resolver])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == "/users/login"


@pytest.mark.anyio
async def test_resolver_raising_does_not_crash_middleware(db_state, caplog):
    """A resolver that raises is logged and the chain continues to the next."""
    import logging

    async def boom(request):
        raise RuntimeError("resolver kaboom")

    async def fallback(request):
        return _ctx(email="fallback@example.com")

    app = await _build_app(db_state, principal_resolvers=[boom, fallback])
    transport = httpx.ASGITransport(app=app)
    with caplog.at_level(logging.ERROR, logger="users.middleware"):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/dashboard")

    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "fallback@example.com"
    assert any("resolver" in rec.message.lower() for rec in caplog.records)


@pytest.mark.anyio
async def test_api_path_unauthenticated_returns_401_json(db_state):
    """Unauthenticated /api/private should return 401 JSON, not a 302 redirect."""
    app = await _build_app(db_state)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/private-thing", follow_redirects=False)

    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"detail": "Not authenticated"}


@pytest.mark.anyio
async def test_view_path_unauthenticated_still_redirects(db_state):
    """View routes (non-/api/*) keep the existing 302-to-login behavior."""
    app = await _build_app(db_state)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == "/users/login"


@pytest.mark.anyio
async def test_session_wins_over_resolver(db_state, mw_active_user):
    """A valid session cookie short-circuits — the resolver chain is not consulted."""
    resolver_called = False

    async def should_not_run(request):
        nonlocal resolver_called
        resolver_called = True
        return _ctx(email="should-not-win@example.com")

    app = await _build_app(db_state, principal_resolvers=[should_not_run])
    transport = httpx.ASGITransport(app=app)
    cookies = _session_cookie({"user_id": str(mw_active_user.id)})
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", cookies=cookies
    ) as client:
        resp = await client.get("/dashboard")

    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "middleware-test@example.com"
    assert resolver_called is False


@pytest.mark.anyio
async def test_resolver_does_not_write_session(db_state):
    """Resolver-authenticated requests must not persist anything to the session."""
    captured = {}

    async def capture(request: Request):
        captured["session"] = dict(request.session)
        user = getattr(request.state, "user", None)
        return JSONResponse({"authenticated": user is not None})

    async def stub_resolver(request):
        return _ctx()

    app = await _build_app(db_state, capture, principal_resolvers=[stub_resolver])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard")

    assert resp.status_code == 200
    assert resp.json() == {"authenticated": True}
    # Session must not contain a user_id, user_ctx, or anything resolver-added.
    assert "user_id" not in captured["session"]
    assert "user_ctx" not in captured["session"]
