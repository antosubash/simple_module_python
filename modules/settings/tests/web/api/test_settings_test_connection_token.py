"""Settings test-connection reaches API tokens: list + run, rate-limited (#1178)."""

from __future__ import annotations

from _api_tokens_support import admin_pat, admin_session, bearer_client, pat_for  # ty: ignore[import-not-found]
from settings.core.constants import Permissions

_BASE = "/api/settings/modules"
_INERTIA = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}


async def test_testable_via_pat_matches_view_prop(app, authenticated_client):
    token = await admin_pat(app, [Permissions.VIEW])
    async with bearer_client(app, token) as bc:
        resp = await bc.get(f"{_BASE}/testable")
    assert resp.status_code == 200, resp.text
    view = await authenticated_client.get("/admin/settings/", headers=_INERTIA)
    assert resp.json() == view.json()["props"]["testable"]
    assert "mail" in resp.json()


async def test_testable_without_scope_is_forbidden(app):
    token = await admin_pat(app, [Permissions.EDIT])
    async with bearer_client(app, token) as bc:
        resp = await bc.get(f"{_BASE}/testable")
    assert resp.status_code == 403


async def test_test_connection_via_pat_matches_view(app, authenticated_client):
    token = await admin_pat(app, [Permissions.VIEW, Permissions.EDIT])
    async with bearer_client(app, token) as bc:
        resp = await bc.post(f"{_BASE}/mail/test-connection")
    assert resp.status_code == 200, resp.text
    view = await authenticated_client.post("/admin/settings/test-connection/mail")
    assert resp.json() == view.json()


async def test_test_connection_with_only_one_of_view_edit_is_forbidden(app):
    for scope in (Permissions.VIEW, Permissions.EDIT):
        token = await admin_pat(app, [scope])
        async with bearer_client(app, token) as bc:
            resp = await bc.post(f"{_BASE}/mail/test-connection")
        assert resp.status_code == 403, scope


async def test_unknown_package_is_404(app):
    token = await admin_pat(app, [Permissions.VIEW, Permissions.EDIT])
    async with bearer_client(app, token) as bc:
        resp = await bc.post(f"{_BASE}/nope/test-connection")
    assert resp.status_code == 404


async def test_rate_limit_is_per_user_not_per_ip_or_token(app):
    owner = await admin_session(app)
    token = await pat_for(app, owner, [Permissions.VIEW, Permissions.EDIT])
    sibling = await pat_for(app, owner, [Permissions.VIEW, Permissions.EDIT])
    other = await admin_pat(app, [Permissions.VIEW, Permissions.EDIT])
    async with bearer_client(app, token) as bc:
        codes = [(await bc.post(f"{_BASE}/mail/test-connection")).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10
    assert codes[10] == 429
    async with bearer_client(app, sibling) as bc:
        assert (await bc.post(f"{_BASE}/mail/test-connection")).status_code == 429
    async with bearer_client(app, other) as bc:
        assert (await bc.post(f"{_BASE}/mail/test-connection")).status_code == 200
