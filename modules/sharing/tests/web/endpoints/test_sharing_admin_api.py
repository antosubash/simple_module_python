"""Admin share listing/revoke over the API with tokens (#1178)."""

from __future__ import annotations

import uuid

import pytest
from _api_tokens_support import CSRF, admin_session, bearer_client, make_admin, pat_for  # ty: ignore[import-not-found]
from _sharing_support import NOTE_TYPE, SharingTestNote, create_note_table, register_note_type
from sharing.core.constants import Permissions
from simple_module_core.access.tenancy import TenantRole
from simple_module_test.web.tenant_client import session_client

LIST_URL = "/api/sharing/admin/shares"
INERTIA = {"X-Inertia": "true", "Accept": "application/json"}


@pytest.fixture
async def note_app(app):
    register_note_type(app.state.sm.resource_types)
    async with app.state.sm.db.engine.begin() as conn:
        await create_note_table(conn)
    return app


async def _share(app, owner, friend) -> None:
    async with app.state.sm.db.session_factory() as session:
        note = SharingTestNote(owner_id=uuid.UUID(owner.user_id), title="n")
        session.add(note)
        await session.commit()
        note_id = str(note.id)
    body = {"resource_type": NOTE_TYPE, "resource_id": note_id, "subject_id": friend.user_id}
    resp = await owner.client.post("/api/sharing/shares", json=body)
    assert resp.status_code == 201, resp.text


async def test_view_pat_lists_shares_like_the_page(note_app, tenant_client):
    async with (
        tenant_client(TenantRole.OWNER) as owner,
        tenant_client(TenantRole.MEMBER, tenant_id=owner.tenant_id) as friend,
    ):
        await _share(note_app, owner, friend)
        data = await admin_session(note_app, owner.tenant_id)
        token = await pat_for(note_app, data, [Permissions.VIEW])
        async with bearer_client(note_app, token) as bc:
            resp = await bc.get(LIST_URL, params={"per_page": 10})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) == {"items", "total", "page", "per_page", "pages"}
        assert body["total"] == 1 and body["per_page"] == 10
        async with session_client(note_app, data) as client:
            page = await client.get("/admin/sharing/", headers=INERTIA)
        view_shares = page.json()["props"]["shares"]
        assert body["items"] == view_shares
        assert set(body["items"][0]) == set(view_shares[0])


async def test_view_pat_cannot_revoke_and_share_pat_cannot_list(note_app, tenant_client):
    async with (
        tenant_client(TenantRole.OWNER) as owner,
        tenant_client(TenantRole.MEMBER, tenant_id=owner.tenant_id) as friend,
    ):
        await _share(note_app, owner, friend)
        data = await admin_session(note_app, owner.tenant_id)
        view_token = await pat_for(note_app, data, [Permissions.VIEW])
        share_token = await pat_for(note_app, data, [Permissions.SHARE])
        async with bearer_client(note_app, view_token) as bc:
            items = (await bc.get(LIST_URL)).json()["items"]
            denied = await bc.post(f"{LIST_URL}/{items[0]['id']}/revoke")
        assert denied.status_code == 403
        async with bearer_client(note_app, share_token) as bc:
            assert (await bc.get(LIST_URL)).status_code == 403


async def test_manage_only_pat_revokes_without_csrf(note_app, tenant_client):
    async with (
        tenant_client(TenantRole.OWNER) as owner,
        tenant_client(TenantRole.MEMBER, tenant_id=owner.tenant_id) as friend,
    ):
        await _share(note_app, owner, friend)
        data = await admin_session(note_app, owner.tenant_id)
        view_token = await pat_for(note_app, data, [Permissions.VIEW])
        manage_token = await pat_for(note_app, data, [Permissions.MANAGE])
        async with bearer_client(note_app, view_token) as bc:
            share_id = (await bc.get(LIST_URL)).json()["items"][0]["id"]
        async with bearer_client(note_app, manage_token) as bc:
            resp = await bc.post(f"{LIST_URL}/{share_id}/revoke")
        assert resp.status_code in (200, 204), resp.text
        async with bearer_client(note_app, view_token) as bc:
            assert (await bc.get(LIST_URL)).json()["total"] == 0


async def test_cookie_revoke_needs_csrf_token(note_app, tenant_client):
    async with (
        tenant_client(TenantRole.OWNER) as owner,
        tenant_client(TenantRole.MEMBER, tenant_id=owner.tenant_id) as friend,
    ):
        await _share(note_app, owner, friend)
        data = await admin_session(note_app, owner.tenant_id)
        async with session_client(note_app, data) as client:
            share_id = (await client.get(LIST_URL)).json()["items"][0]["id"]
            url = f"{LIST_URL}/{share_id}/revoke"
            refused = await client.post(url)
            assert refused.status_code == 403
            assert "X-CSRF-Token" in refused.json()["detail"]
            ok = await client.post(url, headers={"X-CSRF-Token": CSRF})
            assert ok.status_code in (200, 204), ok.text


async def test_strict_tenancy_admin_without_active_tenant_gets_empty_page(note_app):
    email = f"adm-{uuid.uuid4().hex[:8]}@example.com"
    user_id = await make_admin(note_app, email)
    data = {"user_id": user_id, "sm_csrf_token": CSRF}
    async with session_client(note_app, data) as client:
        resp = await client.get(LIST_URL)
        page = await client.get("/admin/sharing/", headers=INERTIA)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["items"], body["total"], body["page"]) == ([], 0, 1)
    assert page.json()["props"]["tenant_required"] is True


async def test_strict_tenancy_admin_revoke_without_active_tenant_is_403(note_app):
    email = f"adm-{uuid.uuid4().hex[:8]}@example.com"
    user_id = await make_admin(note_app, email)
    data = {"user_id": user_id, "sm_csrf_token": CSRF}
    async with session_client(note_app, data) as client:
        resp = await client.post(
            f"{LIST_URL}/{uuid.uuid4()}/revoke", headers={"X-CSRF-Token": CSRF}
        )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "tenant_required"


async def test_revoke_maps_tenant_isolation_without_the_tenants_handler():
    """The endpoint answers 403 itself, so it does not depend on a module's global handler."""
    from fastapi import HTTPException
    from sharing.web.endpoints.admin_api import admin_revoke_share
    from simple_module_db import MissingTenantError

    class Service:
        async def revoke(self, who, share_id):
            raise MissingTenantError("no active tenant")

    with pytest.raises(HTTPException) as err:
        await admin_revoke_share(uuid.uuid4(), Service(), who=None)
    assert err.value.status_code == 403 and err.value.detail == "tenant_required"
