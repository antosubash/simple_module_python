"""Settings test-connection reaches API tokens: list + run, rate-limited (#1178)."""

from __future__ import annotations

import uuid

import httpx
from _api_tokens_support import CSRF, create_pat, join_tenant, make_admin
from settings.core.constants import Permissions
from simple_module_test.web.tenant_client import session_client
from tenants.core.constants import SESSION_ACTIVE_TENANT

_BASE = "/api/settings/modules"
_INERTIA = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}


async def _pat(app, scopes: list[str]) -> str:
    email = f"adm-{uuid.uuid4().hex[:8]}@example.com"
    user_id = await make_admin(app, email)
    tenant_id = await join_tenant(app, user_id, email)
    data = {"user_id": user_id, SESSION_ACTIVE_TENANT: tenant_id, "sm_csrf_token": CSRF}
    async with session_client(app, data) as c:
        return (await create_pat(c, scopes))["token"]


def _bearer(app, token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_testable_via_pat_matches_view_prop(app, authenticated_client):
    token = await _pat(app, [Permissions.VIEW])
    async with _bearer(app, token) as bc:
        resp = await bc.get(f"{_BASE}/testable")
    assert resp.status_code == 200, resp.text
    view = await authenticated_client.get("/admin/settings/", headers=_INERTIA)
    assert resp.json() == view.json()["props"]["testable"]
    assert "mail" in resp.json()


async def test_testable_without_scope_is_forbidden(app):
    token = await _pat(app, [Permissions.EDIT])
    async with _bearer(app, token) as bc:
        resp = await bc.get(f"{_BASE}/testable")
    assert resp.status_code == 403


async def test_test_connection_via_pat_matches_view(app, authenticated_client):
    token = await _pat(app, [Permissions.EDIT])
    async with _bearer(app, token) as bc:
        resp = await bc.post(f"{_BASE}/mail/test-connection")
    assert resp.status_code == 200, resp.text
    view = await authenticated_client.post("/admin/settings/test-connection/mail")
    assert resp.json() == view.json()


async def test_test_connection_without_edit_scope_is_forbidden(app):
    token = await _pat(app, [Permissions.VIEW])
    async with _bearer(app, token) as bc:
        resp = await bc.post(f"{_BASE}/mail/test-connection")
    assert resp.status_code == 403


async def test_unknown_package_is_404(app):
    token = await _pat(app, [Permissions.EDIT])
    async with _bearer(app, token) as bc:
        resp = await bc.post(f"{_BASE}/nope/test-connection")
    assert resp.status_code == 404


async def test_eleventh_call_in_a_minute_is_429(app):
    token = await _pat(app, [Permissions.EDIT])
    async with _bearer(app, token) as bc:
        codes = [(await bc.post(f"{_BASE}/mail/test-connection")).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10
    assert codes[10] == 429
