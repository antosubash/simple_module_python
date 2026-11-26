"""Tenant list/create admit API tokens; switch/leave/accept stay session-only (#1178)."""

from __future__ import annotations

from _api_tokens_support import (  # ty: ignore[import-not-found]
    CSRF,
    admin_session,
    bearer_client,
    join_tenant,
    pat_for,
)
from feature_flags.core.constants import PERM_FEATURE_FLAGS_VIEW
from simple_module_test.web.tenant_client import session_client
from tenants.core.constants import SESSION_ACTIVE_TENANT, Permissions

_URL = "/api/tenants/"


async def _admin_pat(app, scopes: list[str]) -> tuple[str, str, str]:
    data = await admin_session(app)
    return data["user_id"], await pat_for(app, data, scopes), data[SESSION_ACTIVE_TENANT]


async def test_pat_lists_only_its_pinned_tenant(app, user_client):
    async with user_client("other@x.io") as (client, _):
        foreign = await client.post(_URL, json={"name": "Theirs"})
        assert foreign.status_code == 201, foreign.text
    user_id, token, pinned = await _admin_pat(app, [Permissions.PLATFORM_MANAGE])
    # The owner also belongs to a second tenant the token is not pinned to.
    second = await join_tenant(app, user_id, "adm2@example.com")
    async with bearer_client(app, token) as bc:
        resp = await bc.get(_URL)
    assert resp.status_code == 200, resp.text
    assert [t["id"] for t in resp.json()] == [pinned]
    assert second != pinned


async def test_pat_with_platform_manage_creates_tenant_without_cookie(app):
    _, token, _t = await _admin_pat(app, [Permissions.PLATFORM_MANAGE])
    app.state.tenants.settings.allow_self_service = False
    async with bearer_client(app, token) as bc:
        resp = await bc.post(_URL, json={"name": "Via Token"})
        assert resp.status_code == 201, resp.text
        assert resp.json()["role"] == "owner"
        assert "set-cookie" not in resp.headers
        names = [t["name"] for t in (await bc.get(_URL)).json()]
    # The token stays pinned to its own tenant; the new one is not listed.
    assert names == ["Test Org"]


async def test_pat_without_platform_manage_blocked_whatever_self_service_says(app):
    _, token, _t = await _admin_pat(app, [PERM_FEATURE_FLAGS_VIEW])
    for allowed in (False, True):
        app.state.tenants.settings.allow_self_service = allowed
        async with bearer_client(app, token) as bc:
            resp = await bc.post(_URL, json={"name": "Nope"})
        assert resp.status_code == 403, (allowed, resp.text)
        assert resp.json()["detail"] == "self_service_disabled"


async def test_session_only_routes_refuse_tokens(app):
    _, token, _t = await _admin_pat(app, [Permissions.PLATFORM_MANAGE])
    async with bearer_client(app, token) as bc:
        for method, url, kw in (
            ("POST", "/api/tenants/some-id/switch", {}),
            ("DELETE", "/api/tenants/current/membership", {}),
            ("POST", "/api/tenants/invitations/accept", {"json": {"token": "x"}}),
        ):
            resp = await bc.request(method, url, **kw)
            assert resp.status_code == 403, (url, resp.text)
            assert "API tokens cannot be used" in resp.text, (url, resp.text)


async def _active_tenant(client) -> str | None:
    page = await client.get(
        "/tenants/", headers={"X-Inertia": "true", "Accept": "application/json"}
    )
    assert page.status_code == 200, page.text
    active = page.json()["props"]["tenant"]["active"]
    return active["id"] if active else None


async def test_session_switch_still_works(user_client):
    async with user_client("s@x.io") as (client, _):
        first = (await client.post(_URL, json={"name": "One"})).json()
        second = (await client.post(_URL, json={"name": "Two"})).json()
        assert await _active_tenant(client) == second["id"]  # creating switches to it
        assert (await client.post(f"/api/tenants/{first['id']}/switch")).status_code == 204
        assert await _active_tenant(client) == first["id"]


async def test_pat_cannot_suspend_its_own_tenant(app):
    from tenants.models import Tenant

    _, token, pinned = await _admin_pat(app, [Permissions.PLATFORM_MANAGE])
    _, _tok2, other = await _admin_pat(app, [Permissions.PLATFORM_MANAGE])
    async with bearer_client(app, token) as bc:
        own = await bc.post(f"/api/tenants/admin/{pinned}/suspend")
        assert own.status_code == 409, own.text
        assert own.json()["detail"] == "cannot_suspend_own_tenant"
        assert (await bc.post(f"/api/tenants/admin/{other}/suspend")).status_code == 200
    async with app.state.sm.db.session_factory() as s:
        from simple_module_db.scoping.tenancy import all_tenants

        with all_tenants():
            assert (await s.get(Tenant, pinned)).status == "active"


async def test_session_admin_suspend_unchanged(app):
    from simple_module_db.scoping.tenancy import all_tenants
    from tenants.models import Tenant

    data = await admin_session(app)
    tenant_id = data[SESSION_ACTIVE_TENANT]
    async with session_client(app, data) as c:
        resp = await c.post(
            f"/api/tenants/admin/{tenant_id}/suspend", headers={"X-CSRF-Token": CSRF}
        )
    assert resp.status_code == 200, resp.text
    async with app.state.sm.db.session_factory() as s:
        with all_tenants():
            assert (await s.get(Tenant, tenant_id)).status == "suspended"
