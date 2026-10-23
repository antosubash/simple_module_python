"""SharingService: grant validation, expiry, revoke, tenant isolation (GH #526)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from _sharing_support import (
    NOTE_POLICY,
    NOTE_TYPE,
    FakeDirectory,
    SharingTestNote,
    create_note_table,
    register_note_type,
)
from sharing.constants import PERM_MANAGE
from sharing.contracts.schemas import ShareGrant
from sharing.models import ResourceShare
from sharing.service import SharingError, SharingService
from simple_module_core.resources import (
    ACTION_EDIT,
    ACTION_SHARE,
    ACTION_VIEW,
    ResourcePrincipal,
    ResourceTypeRegistry,
)
from simple_module_db.tenancy import tenant_context
from sqlmodel import select

OWNER, FRIEND, STRANGER = (str(uuid.UUID(int=n)) for n in (1, 2, 3))


def _who(user_id: str) -> ResourcePrincipal:
    return ResourcePrincipal(user_id=user_id)


@pytest.fixture
async def env(db_session):
    await create_note_table(await db_session.connection())
    note = SharingTestNote(owner_id=uuid.UUID(OWNER), title="n")
    db_session.add(note)
    await db_session.flush()
    registry = ResourceTypeRegistry()
    register_note_type(registry)
    service = SharingService(db_session, registry, FakeDirectory(OWNER, FRIEND, STRANGER))
    return service, str(note.id)


async def _visible(session, user_id: str, action: str = ACTION_VIEW) -> list[str]:
    stmt = NOTE_POLICY.filter(_who(user_id), action, select(SharingTestNote))
    return [n.title for n in (await session.execute(stmt)).scalars()]


def _grant(note_id: str, **kw) -> ShareGrant:
    return ShareGrant(resource_type=NOTE_TYPE, resource_id=note_id, subject_id=FRIEND, **kw)


async def _refused(coro, status: int) -> None:
    with pytest.raises(SharingError) as info:
        await coro
    assert info.value.status_code == status


async def test_grant_makes_row_visible_to_grantee_only(env):
    service, note_id = env
    with tenant_context("t1"):
        assert await _visible(service.db, FRIEND) == []
        share = await service.grant(_who(OWNER), _grant(note_id))
        assert share.resource_id == uuid.UUID(note_id).hex
        assert await _visible(service.db, FRIEND) == ["n"]
        assert await _visible(service.db, FRIEND, ACTION_EDIT) == []
        assert await _visible(service.db, STRANGER) == []


async def test_edit_role_and_regrant_updates_in_place(env):
    service, note_id = env
    with tenant_context("t1"):
        await service.grant(_who(OWNER), _grant(note_id))
        await service.grant(_who(OWNER), _grant(note_id, role=ACTION_EDIT))
        rows = (await service.db.execute(select(ResourceShare))).scalars().all()
        assert [r.role for r in rows] == [ACTION_EDIT]
        assert await _visible(service.db, FRIEND, ACTION_EDIT) == ["n"]


async def test_expired_share_hides_the_row(env):
    service, note_id = env
    with tenant_context("t1"):
        share = await service.grant(_who(OWNER), _grant(note_id))
        share.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await service.db.flush()
        assert await _visible(service.db, FRIEND) == []


async def test_share_from_another_tenant_does_not_apply(env):
    service, note_id = env
    with tenant_context("t1"):
        await service.grant(_who(OWNER), _grant(note_id))
    with tenant_context("t2"):
        assert await _visible(service.db, FRIEND) == []
        await _refused(service.revoke(_who(OWNER), uuid.uuid4()), 404)


async def test_grant_validation(env):
    service, note_id = env
    with tenant_context("t1"):
        bad_type = ShareGrant(resource_type="nope.thing", resource_id=note_id, subject_id=FRIEND)
        await _refused(service.grant(_who(OWNER), bad_type), 422)
        await _refused(service.grant(_who(STRANGER), _grant(note_id)), 404)
        unknown = _grant(note_id).model_copy(update={"subject_id": str(uuid.uuid4())})
        await _refused(service.grant(_who(OWNER), unknown), 422)
        await _refused(service.grant(_who(OWNER), _grant(note_id, role=ACTION_SHARE)), 422)
        past = datetime.now(UTC) - timedelta(days=1)
        await _refused(service.grant(_who(OWNER), _grant(note_id, expires_at=past)), 422)
        await _refused(service.grant(_who(OWNER), _grant("not-a-uuid")), 404)
        to_self = _grant(note_id).model_copy(update={"subject_id": OWNER})
        await _refused(service.grant(_who(OWNER), to_self), 422)


async def test_viewer_may_not_reshare(env):
    service, note_id = env
    with tenant_context("t1"):
        await service.grant(_who(OWNER), _grant(note_id))
        reshare = _grant(note_id).model_copy(update={"subject_id": STRANGER})
        await _refused(service.grant(_who(FRIEND), reshare), 403)


async def test_revoke_hard_deletes(env):
    service, note_id = env
    with tenant_context("t1"):
        share = await service.grant(_who(OWNER), _grant(note_id))
        await _refused(service.revoke(_who(STRANGER), share.id), 404)
        await service.revoke(_who(OWNER), share.id)
        stmt = select(ResourceShare).execution_options(include_deleted=True)
        assert (await service.db.execute(stmt)).scalars().all() == []


async def test_grantee_may_leave_and_owner_lists(env):
    service, note_id = env
    with tenant_context("t1"):
        share = await service.grant(_who(OWNER), _grant(note_id))
        listed = await service.for_resource(_who(OWNER), NOTE_TYPE, note_id)
        assert [s.id for s in listed] == [share.id]
        await _refused(service.for_resource(_who(FRIEND), NOTE_TYPE, note_id), 403)
        await service.revoke(_who(FRIEND), share.id)
        assert await _visible(service.db, FRIEND) == []


@pytest.mark.parametrize("role", [ACTION_VIEW, ACTION_EDIT])
async def test_grantee_cannot_manage_shares_even_with_edit_role(env, role):
    service, note_id = env
    with tenant_context("t1"):
        await service.grant(_who(OWNER), _grant(note_id, role=role))
        reshare = _grant(note_id).model_copy(update={"subject_id": STRANGER})
        await _refused(service.grant(_who(FRIEND), reshare), 403)
        await _refused(service.for_resource(_who(FRIEND), NOTE_TYPE, note_id), 403)
        assert len(await service.for_resource(_who(OWNER), NOTE_TYPE, note_id)) == 1


@pytest.mark.parametrize("actor", [OWNER, FRIEND, "admin"])
async def test_real_share_id_cannot_be_revoked_across_tenants(env, actor):
    service, note_id = env
    who = (
        ResourcePrincipal(user_id=actor, permissions=frozenset({PERM_MANAGE}))
        if actor == "admin"
        else _who(actor)
    )
    with tenant_context("t1"):
        share = await service.grant(_who(OWNER), _grant(note_id))
    with tenant_context("t2"):
        await _refused(service.revoke(who, share.id), 404)
    with tenant_context("t1"):
        assert [s.id for s in await service.for_resource(_who(OWNER), NOTE_TYPE, note_id)] == [
            share.id
        ]
        assert await _visible(service.db, FRIEND) == ["n"]


async def test_admin_may_revoke_without_resource_ownership(env):
    service, note_id = env
    admin = ResourcePrincipal(user_id=STRANGER, permissions=frozenset({PERM_MANAGE}))
    with tenant_context("t1"):
        share = await service.grant(_who(OWNER), _grant(note_id))
        await service.revoke(admin, share.id)
        assert await service.for_resource(_who(OWNER), NOTE_TYPE, note_id) == []
        assert await _visible(service.db, FRIEND) == []
        await _refused(service.revoke(admin, share.id), 404)


async def test_expired_share_can_be_renewed_without_duplicate_grants(env):
    service, note_id = env
    with tenant_context("t1"):
        share = await service.grant(_who(OWNER), _grant(note_id))
        share.expires_at = datetime.now(UTC) - timedelta(days=1)
        await service.db.flush()
        assert await _visible(service.db, FRIEND) == []
        assert [s.id for s in await service.for_resource(_who(OWNER), NOTE_TYPE, note_id)] == [
            share.id
        ]
        future = datetime.now(UTC) + timedelta(days=1)
        renewed = await service.grant(
            _who(OWNER), _grant(note_id, expires_at=future, role=ACTION_EDIT)
        )
        assert renewed.id == share.id
        assert await _visible(service.db, FRIEND, ACTION_EDIT) == ["n"]
        assert len(await service.for_resource(_who(OWNER), NOTE_TYPE, note_id)) == 1
