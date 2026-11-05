"""Grantees and user labels stay inside the active tenant (GH #526 review)."""

from __future__ import annotations

import uuid

import pytest
from _sharing_support import NOTE_TYPE, SharingTestNote, create_note_table, register_note_type
from sharing.models import ResourceShare
from simple_module_core.tenancy import TenantRole, tenant_member_ids
from simple_module_db.tenancy import tenant_context

SHARES = "/api/sharing/shares"


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


def _body(note_id: str, subject_id: str) -> dict:
    return {"resource_type": NOTE_TYPE, "resource_id": note_id, "subject_id": subject_id}


async def test_cross_tenant_grantee_gets_the_unknown_user_error(note_app, tenant_client):
    async with tenant_client(TenantRole.OWNER) as owner, tenant_client() as outsider:
        note_id = await _note(note_app, owner.user_id)
        foreign = await owner.client.post(SHARES, json=_body(note_id, outsider.user_id))
        ghost = await owner.client.post(SHARES, json=_body(note_id, str(uuid.uuid4())))
        assert foreign.status_code == ghost.status_code == 422
        assert foreign.json() == ghost.json()


async def test_same_tenant_grantee_is_accepted_and_labelled(note_app, tenant_client):
    async with (
        tenant_client(TenantRole.OWNER) as owner,
        tenant_client(TenantRole.MEMBER, tenant_id=owner.tenant_id) as friend,
    ):
        note_id = await _note(note_app, owner.user_id)
        resp = await owner.client.post(SHARES, json=_body(note_id, friend.user_id))
        assert resp.status_code == 201
        assert resp.json()["subject_label"] and resp.json()["granted_by_label"]


async def test_labels_of_users_outside_the_tenant_are_withheld(note_app, tenant_client):
    async with tenant_client(TenantRole.OWNER) as owner, tenant_client() as outsider:
        note_id = await _note(note_app, owner.user_id)
        # A share whose subject is not a member (left the tenant, or legacy data).
        async with note_app.state.sm.db.session_factory() as session:
            with tenant_context(owner.tenant_id):
                session.add(
                    ResourceShare(
                        resource_type=NOTE_TYPE,
                        resource_id=uuid.UUID(note_id).hex,
                        subject_id=outsider.user_id,
                        role="view",
                        granted_by=owner.user_id,
                    )
                )
                await session.commit()
        listed = await owner.client.get(
            SHARES, params={"resource_type": NOTE_TYPE, "resource_id": note_id}
        )
        (share,) = listed.json()
        assert share["subject_id"] == outsider.user_id
        assert share["subject_label"] is None
        assert share["granted_by_label"]


async def test_tenant_member_ids_seam(note_app, tenant_client):
    async with tenant_client(TenantRole.OWNER) as owner, tenant_client() as outsider:
        async with note_app.state.sm.db.session_factory() as db:
            found = await tenant_member_ids(
                note_app, db, owner.tenant_id, [owner.user_id, outsider.user_id]
            )
        assert found == {owner.user_id}
