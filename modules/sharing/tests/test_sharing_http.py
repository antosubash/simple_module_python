"""Sharing over HTTP: grant/list/revoke API and the admin page (GH #526)."""

from __future__ import annotations

import uuid

import pytest
from _sharing_support import NOTE_TYPE, SharingTestNote, create_note_table, register_note_type
from sharing.constants import PERM_SHARE
from sharing.policy import share_exists_for
from simple_module_core.resources import ACTION_SHARE, ACTION_VIEW, ResourceType
from simple_module_core.tenancy import TenantRole
from simple_module_db.resource_policy import OwnedResourcePolicy, select_by_id
from simple_module_test.tenant_client import session_client

SHARES = "/api/sharing/shares"
INERTIA = {"X-Inertia": "true", "Accept": "application/json"}


@pytest.fixture
async def note_app(app):
    register_note_type(app.state.sm.resource_types)
    async with app.state.sm.db.engine.begin() as conn:
        await create_note_table(conn)
    return app


async def _note(app, owner_id: str) -> str:
    async with app.state.sm.db.session_factory() as session:
        note = SharingTestNote(owner_id=uuid.UUID(owner_id), title="n")
        session.add(note)
        await session.commit()
        return str(note.id)


def _body(note_id: str, subject_id: str, **kw) -> dict:
    return {"resource_type": NOTE_TYPE, "resource_id": note_id, "subject_id": subject_id, **kw}


async def test_owner_grants_lists_and_revokes(note_app, tenant_client):
    async with (
        tenant_client(TenantRole.OWNER) as owner,
        tenant_client(TenantRole.MEMBER, tenant_id=owner.tenant_id) as friend,
    ):
        note_id = await _note(note_app, owner.user_id)
        resp = await owner.client.post(SHARES, json=_body(note_id, friend.user_id))
        assert resp.status_code == 201, resp.text
        share = resp.json()
        assert share["subject_label"] and share["role"] == "view"

        query = {"resource_type": NOTE_TYPE, "resource_id": note_id}
        listed = await owner.client.get(SHARES, params=query)
        assert [s["id"] for s in listed.json()] == [share["id"]]
        assert (await friend.client.get(SHARES, params=query)).status_code == 403

        gone = await owner.client.delete(f"{SHARES}/{share['id']}")
        assert gone.status_code == 204
        assert (await owner.client.get(SHARES, params=query)).json() == []


async def test_grant_refusals(note_app, tenant_client):
    async with tenant_client(TenantRole.OWNER) as owner, tenant_client() as outsider:
        note_id = await _note(note_app, owner.user_id)
        refused = await outsider.client.post(SHARES, json=_body(note_id, owner.user_id))
        assert refused.status_code == 404
        unknown_type = {**_body(note_id, outsider.user_id), "resource_type": "nope.thing"}
        assert (await owner.client.post(SHARES, json=unknown_type)).status_code == 422
        ghost = _body(note_id, str(uuid.uuid4()))
        assert (await owner.client.post(SHARES, json=ghost)).status_code == 422


async def test_admin_page_lists_tenant_shares(note_app, tenant_client):
    from tenants.constants import SESSION_ACTIVE_TENANT
    from tenants.models import Membership
    from tenants.resolver import forget
    from users.bootstrap import create_admin

    async with tenant_client(TenantRole.OWNER) as owner:
        async with tenant_client(TenantRole.MEMBER, tenant_id=owner.tenant_id) as friend:
            note_id = await _note(note_app, owner.user_id)
            await owner.client.post(SHARES, json=_body(note_id, friend.user_id))
        async with note_app.state.sm.db.session_factory() as session:
            admin = await create_admin(
                session, email="share-admin@example.com", password="pw-12345"
            )
            admin_id = str(admin.user.id)
            session.add(
                Membership(
                    tenant_id=owner.tenant_id,
                    user_id=admin_id,
                    role=TenantRole.OWNER,
                    email="share-admin@example.com",
                )
            )
            await session.commit()
        forget(admin_id)
        data = {"user_id": admin_id, SESSION_ACTIVE_TENANT: owner.tenant_id}
        async with session_client(note_app, data) as client:
            resp = await client.get("/admin/sharing/", headers=INERTIA)
            assert resp.status_code == 200, resp.text
            props = resp.json()["props"]
            assert props["total"] == 1 and props["can_revoke"] is True
            share_id = props["shares"][0]["id"]
            revoked = await client.post(f"/admin/sharing/{share_id}/revoke")
            assert revoked.status_code == 303
        # A plain tenant owner holds sharing.share but not the admin page.
        assert (await owner.client.get("/admin/sharing/")).status_code == 403


async def test_custom_manager_uses_api_but_still_needs_permission(app, tenant_client, monkeypatch):
    roles = {"manager": (ACTION_VIEW, ACTION_SHARE), "reviewer": (ACTION_VIEW, "review")}
    policy = OwnedResourcePolicy(
        SharingTestNote.owner_id,
        bypass_perm=None,
        share_exists=share_exists_for(NOTE_TYPE, SharingTestNote.id, roles=roles),
    )
    app.state.sm.resource_types.register(
        ResourceType(NOTE_TYPE, policy, select_by_id(SharingTestNote), share_roles=roles)
    )
    async with app.state.sm.db.engine.begin() as conn:
        await create_note_table(conn)
    async with (
        tenant_client() as owner,
        tenant_client(tenant_id=owner.tenant_id) as manager,
        tenant_client(tenant_id=owner.tenant_id) as reader,
    ):
        note_id = await _note(app, owner.user_id)
        response = await owner.client.post(
            SHARES, json=_body(note_id, manager.user_id, role="manager")
        )
        assert response.status_code == 201, response.text
        query = {"resource_type": NOTE_TYPE, "resource_id": note_id}
        assert (await manager.client.get(SHARES, params=query)).status_code == 200
        response = await manager.client.post(
            SHARES, json=_body(note_id, reader.user_id, role="reviewer")
        )
        assert response.status_code == 201, response.text
        share_id = response.json()["id"]
        assert (await manager.client.delete(f"{SHARES}/{share_id}")).status_code == 204
        # Removing the API permission must refuse even an active resource manager.
        registry = app.state.sm.permissions
        denied_map = {
            role: [key for key in keys if key != PERM_SHARE]
            for role, keys in registry.role_map.items()
        }
        monkeypatch.setattr(type(registry), "role_map", property(lambda self: denied_map))
        assert (await manager.client.get(SHARES, params=query)).status_code == 403
        assert (
            await manager.client.post(SHARES, json=_body(note_id, reader.user_id, role="manager"))
        ).status_code == 403
        assert (await manager.client.delete(f"{SHARES}/{share_id}")).status_code == 403
