"""Tenant list/create admit API tokens; switch/leave/accept stay session-only (#1178)."""

from __future__ import annotations

import uuid

from _api_tokens_support import CSRF, create_pat
from feature_flags.core.constants import PERM_FEATURE_FLAGS_VIEW
from simple_module_test.web.tenant_client import session_client
from tenants.core.constants import SESSION_ACTIVE_TENANT, Permissions

_URL = "/api/tenants/"


async def _bearer_client(app, token: str):
    import httpx

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


async def _admin_pat(app, scopes: list[str]) -> tuple[str, str, str]:
    from _api_tokens_support import join_tenant, make_admin

    email = f"adm-{uuid.uuid4().hex[:8]}@example.com"
    user_id = await make_admin(app, email)
    tenant_id = await join_tenant(app, user_id, email)
    data = {"user_id": user_id, SESSION_ACTIVE_TENANT: tenant_id, "sm_csrf_token": CSRF}
    async with session_client(app, data) as c:
        body = await create_pat(c, scopes)
    return user_id, body["token"], tenant_id


async def test_pat_lists_only_its_pinned_tenant(app, user_client):
    async with user_client("other@x.io") as (client, _):
        foreign = await client.post(_URL, json={"name": "Theirs"})
        assert foreign.status_code == 201, foreign.text
    user_id, token, pinned = await _admin_pat(app, [Permissions.PLATFORM_MANAGE])
    from _api_tokens_support import join_tenant

    # The owner also belongs to a second tenant the token is not pinned to.
    second = await join_tenant(app, user_id, "adm2@example.com")
    async with await _bearer_client(app, token) as bc:
        resp = await bc.get(_URL)
    assert resp.status_code == 200, resp.text
    assert [t["id"] for t in resp.json()] == [pinned]
    assert second != pinned


async def test_pat_with_platform_manage_creates_tenant_without_cookie(app):
    _, token, _t = await _admin_pat(app, [Permissions.PLATFORM_MANAGE])
    app.state.tenants.settings.allow_self_service = False
    async with await _bearer_client(app, token) as bc:
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
        async with await _bearer_client(app, token) as bc:
            resp = await bc.post(_URL, json={"name": "Nope"})
        assert resp.status_code == 403, (allowed, resp.text)
        assert resp.json()["detail"] == "self_service_disabled"


async def test_session_only_routes_refuse_tokens(app):
    _, token, _t = await _admin_pat(app, [Permissions.PLATFORM_MANAGE])
    async with await _bearer_client(app, token) as bc:
        for method, url, kw in (
            ("POST", "/api/tenants/some-id/switch", {}),
            ("DELETE", "/api/tenants/current/membership", {}),
            ("POST", "/api/tenants/invitations/accept", {"json": {"token": "x"}}),
        ):
            resp = await bc.request(method, url, **kw)
            assert resp.status_code == 403, (url, resp.text)
            assert "API tokens cannot be used" in resp.text, (url, resp.text)


async def test_session_switch_still_works(user_client):
    async with user_client("s@x.io") as (client, user_id):
        t = (await client.post(_URL, json={"name": "One"})).json()
        assert (await client.post(f"/api/tenants/{t['id']}/switch")).status_code == 204
        assert user_id
