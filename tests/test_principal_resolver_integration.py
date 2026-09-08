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
async def test_a_bad_bearer_is_not_rescued_by_a_valid_session(authenticated_client):
    """An explicitly presented credential that is invalid fails the request.

    This test previously asserted the opposite — that the session cookie wins
    and "the resolver is not consulted" — and had never run: ``testpaths`` did
    not list ``tests/``, so a bare ``pytest`` collected nothing here. The
    behaviour it described is not what ``UsersAuthProvider.resolve_user`` does;
    the ``Authorization`` header is checked first and a bad token returns
    ``None`` without falling through.

    Keeping the code and correcting the test is the deliberate call. Falling
    through would make an invalid token indistinguishable from no token at all,
    so a client whose credential has expired or been revoked silently keeps
    working on whatever other identity it happens to carry, and its 401s become
    dependent on what else is in the request. Nothing is gained by the
    fall-through either: it can only ever resolve the session's own identity,
    which the caller already had.

    The narrow cost is a browser that attaches a stale ``Authorization`` header
    to a page request. Nothing in this app does that — pages authenticate with
    the session cookie.
    """
    resp = await authenticated_client.get(
        "/api/permissions/",
        headers={"Authorization": "Bearer bad"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_the_same_session_succeeds_without_the_bad_header(authenticated_client):
    """The other half: the session itself is fine, so the 401 above is the
    header's doing and not a broken fixture."""
    resp = await authenticated_client.get("/api/permissions/")
    assert resp.status_code == 200
