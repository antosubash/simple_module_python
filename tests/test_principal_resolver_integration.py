"""End-to-end test: a fake bearer-token resolver authenticates against the full app stack."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from auth import UserContext  # exercises the documented public re-export


@pytest.fixture
async def app_with_pat_resolver(app):
    """Reuses the standard ``app`` fixture and appends a fake bearer-token resolver.

    The resolver recognizes a single hardcoded token ``"good"`` mapped to a
    deterministic UserContext. ``"bad"`` (or absent header) returns None.
    """

    async def fake_pat_resolver(request) -> UserContext | None:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header.removeprefix("Bearer ")
        if token != "good":
            return None
        return UserContext(
            id="22222222-2222-2222-2222-222222222222",
            email="pat-user@example.com",
            name="PAT User",
            roles=["admin"],
            tenant_id=None,
        )

    app.state.auth.principal_resolvers.append(fake_pat_resolver)
    yield app
    app.state.auth.principal_resolvers.remove(fake_pat_resolver)


@pytest.fixture
async def pat_client(app_with_pat_resolver) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app_with_pat_resolver)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.mark.anyio
async def test_bearer_token_authenticates_against_protected_view(pat_client):
    """Valid bearer token -> 200 on a protected view path (users admin)."""
    resp = await pat_client.get(
        "/admin/users/",
        headers={"Authorization": "Bearer good"},
        follow_redirects=False,
    )
    # /admin/users/ is a view route; with a valid resolver the request gets
    # through AuthMiddleware (200) instead of redirecting to /users/login.
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_invalid_bearer_token_returns_401_on_api_path(pat_client):
    """Bad bearer on an /api/* path -> 401 JSON, not a redirect."""
    resp = await pat_client.get(
        "/api/users/admin",
        headers={"Authorization": "Bearer bad"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Not authenticated"}


@pytest.mark.anyio
async def test_no_auth_header_on_api_returns_401(pat_client):
    """No Authorization header on a private /api/* path -> 401 JSON."""
    resp = await pat_client.get("/api/users/admin", follow_redirects=False)
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Not authenticated"}


@pytest.mark.anyio
async def test_session_wins_over_bad_bearer(authenticated_client):
    """A valid session cookie + Bearer bad -> 200 via session; resolver not consulted.

    The ``authenticated_client`` fixture already carries an admin session cookie;
    here we additionally send a bad bearer to prove the session path wins.
    Endpoint is any admin-readable, non-user-enumerating route."""
    resp = await authenticated_client.get(
        "/api/permissions/",
        headers={"Authorization": "Bearer bad"},
    )
    assert resp.status_code == 200
