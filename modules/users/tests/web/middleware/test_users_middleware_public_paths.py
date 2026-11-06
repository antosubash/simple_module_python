"""AuthMiddleware tests for PUBLIC_PATHS — paths that must pass through
unauthenticated.

Helpers + fixtures live in ``_middleware_support`` alongside the full
middleware tests in ``test_users_middleware``.
"""

from __future__ import annotations

import httpx
import pytest
from _middleware_support import _build_app, _session_cookie


@pytest.mark.anyio
async def test_public_path_unauthenticated_passes_through(db_state):
    app = await _build_app(db_state)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/users/login", follow_redirects=False)

    assert resp.status_code == 200


@pytest.mark.anyio
async def test_api_users_auth_prefix_is_public(db_state):
    app = await _build_app(db_state)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/users/auth/login", follow_redirects=False)

    assert resp.status_code == 200


@pytest.mark.anyio
async def test_health_path_is_public(db_state):
    app = await _build_app(db_state)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health", follow_redirects=False)

    assert resp.status_code == 200


@pytest.mark.anyio
async def test_root_path_with_valid_user_sets_context(db_state, mw_active_user):
    """The root path ``/`` is public, but if a valid session cookie is present
    the middleware should still hydrate ``request.state.user`` so authenticated
    visitors see "Open Dashboard" instead of "Get Started"."""
    app = await _build_app(db_state)
    transport = httpx.ASGITransport(app=app)
    cookies = _session_cookie({"user_id": str(mw_active_user.id)})
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", cookies=cookies
    ) as client:
        resp = await client.get("/", follow_redirects=False)

    assert resp.status_code == 200
    data = resp.json()
    assert data["user"] is not None
    assert data["user"]["email"] == "middleware-test@example.com"
