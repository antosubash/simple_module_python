"""Tokens reach only permission-gated API routes (security review M1, L2).

Routes that need nothing but a signed-in principal — create or leave an
organisation, the profile page, the dashboard — used to accept any token,
whatever it was scoped to. ``simple_module_hosting.token_guard`` now refuses a
token on every route without a permission gate, and on every page.
"""

from __future__ import annotations

import uuid
from typing import Any

from _api_tokens_support import (
    CSRF_HEADERS,
    FLAGS_URL,
    INERTIA_HEADERS,
    SERVICE_URL,
    create_pat,
    join_tenant,
)
from simple_module_test.tenant_client import create_user


async def _memberships(app: Any, user_id: str) -> list[str]:
    from sqlalchemy import select
    from tenants.models import Membership

    async with app.state.sm.db.session_factory() as session:
        rows = await session.execute(
            select(Membership.tenant_id).where(Membership.user_id == user_id)
        )
        return [r[0] for r in rows]


async def test_pat_cannot_use_tenant_self_service_routes(app, actor, bearer):
    async with actor() as u:
        token = (await create_pat(u.client, ["api_tokens.use"]))["token"]
        other = f"o-{uuid.uuid4().hex[:6]}@example.com"
        await join_tenant(app, await create_user(app, other), other, u.tenant_id)
        before = await _memberships(app, u.user_id)

    assert (await bearer("GET", "/api/tenants/", token)).status_code == 403
    created = await bearer("POST", "/api/tenants/", token, json={"name": "Evil Org"})
    assert created.status_code == 403
    assert created.headers["content-type"].startswith("application/json")
    left = await bearer("DELETE", "/api/tenants/current/membership", token)
    assert left.status_code == 403
    switch = await bearer("POST", f"/api/tenants/{u.tenant_id}/switch", token)
    assert switch.status_code == 403
    accept = await bearer("POST", "/api/tenants/invitations/accept", token, json={"token": "x"})
    assert accept.status_code == 403
    # Nothing happened: no new organisation, still a member.
    assert await _memberships(app, u.user_id) == before


async def test_pat_cannot_open_pages(actor, bearer):
    async with actor(admin=True) as a:
        token = (await create_pat(a.client, ["api_tokens.use", "feature_flags.view"]))["token"]

    for path in ("/users/me", "/dashboard/", "/api-tokens/", "/tenants/"):
        resp = await bearer("GET", path, token, headers=INERTIA_HEADERS)
        assert resp.status_code == 403, path


async def test_pat_still_reads_a_permission_gated_api_route(actor, bearer):
    async with actor(admin=True) as a:
        token = (await create_pat(a.client, ["feature_flags.view"]))["token"]
    assert (await bearer("GET", FLAGS_URL, token)).status_code == 200


async def test_the_browser_session_is_unaffected(actor):
    async with actor() as u:
        assert (await u.client.get("/api/tenants/")).status_code == 200
        assert (await u.client.get("/users/me", headers=INERTIA_HEADERS)).status_code == 200


async def test_token_on_a_public_route_is_served_as_anonymous(actor, bearer):
    async with actor() as u:
        token = (await create_pat(u.client, ["api_tokens.use"]))["token"]
    assert (await bearer("GET", "/health/live", token)).status_code == 200


async def _service_key(app, actor, scopes: list[str], roles: list[str]) -> str:
    async with actor(admin=True) as a:
        resp = await a.client.post(
            SERVICE_URL,
            json={"name": "k", "roles": roles, "scopes": scopes, "expires_in_days": 30},
            headers=CSRF_HEADERS,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["token"]


async def test_service_key_cannot_create_an_organisation(app, actor, bearer):
    app.state.sm.permissions.map_role("user", ["feature_flags.view"])
    token = await _service_key(app, actor, ["feature_flags.view"], ["user"])
    assert (await bearer("POST", "/api/tenants/", token, json={"name": "Svc"})).status_code == 403
    me = await bearer("GET", "/users/me", token, headers=INERTIA_HEADERS)
    assert me.status_code == 403  # was a 500: uuid.UUID("svc:…")


def _parameterless_get_paths(app) -> list[str]:
    """Every GET under ``/api/`` with no path parameter, from the OpenAPI schema."""
    paths = app.openapi()["paths"]
    return sorted(
        p for p, ops in paths.items() if "get" in ops and "{" not in p and p.startswith("/api/")
    )


async def test_a_broad_service_key_never_causes_a_500(app, actor, bearer):
    """L2: a ``svc:`` principal on any token-reachable route fails closed, never 500s."""
    registry = app.state.sm.permissions
    every = sorted(p for p in registry.all_permissions if p != "*")
    registry.map_role("user", every)
    token = await _service_key(app, actor, every, ["user"])
    failures = []
    for path in _parameterless_get_paths(app):
        resp = await bearer("GET", path, token)
        if resp.status_code >= 500:
            failures.append((path, resp.status_code))
    assert failures == []
