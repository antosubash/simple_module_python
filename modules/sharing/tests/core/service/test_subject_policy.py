"""Role and custom shares use one tenant-scoped access query (#963)."""

import uuid
from dataclasses import replace

import pytest
from _sharing_support import NOTE_POLICY, NOTE_TYPE, SharingTestNote, create_note_table
from sharing.contracts import SubjectProvider
from sharing.contracts.subjects import SUBJECTS_KEY
from sharing.core.subjects import default_subject_registry
from sharing.models import ResourceShare
from simple_module_core.access.resources import ResourcePrincipal
from simple_module_core.access.tenancy import TenantRole, tenant_role
from simple_module_db.tenancy import tenant_context
from sqlalchemy import event
from sqlmodel import select


@pytest.fixture
async def role_notes(db_session):
    await create_note_table(await db_session.connection())
    notes = [SharingTestNote(owner_id=uuid.uuid4(), title=str(i)) for i in range(12)]
    db_session.add_all(notes)
    await db_session.flush()
    with tenant_context("a"):
        db_session.add_all(
            [
                ResourceShare(
                    resource_type=NOTE_TYPE,
                    resource_id=n.id.hex,
                    subject_type="tenant_role",
                    subject_id="member",
                    role="view",
                    granted_by="owner",
                )
                for n in notes
            ]
        )
        await db_session.flush()
    return notes


async def visible(db, who):
    return list(
        (await db.execute(NOTE_POLICY.filter(who, "view", select(SharingTestNote)))).scalars()
    )


async def test_role_change_revokes_and_tenants_do_not_leak(db_session, role_notes):
    member = ResourcePrincipal(
        "friend", roles=frozenset({tenant_role(TenantRole.MEMBER)}), tenant_id="a"
    )
    with tenant_context("a"):
        assert len(await visible(db_session, member)) == 12
        assert (
            await visible(
                db_session, replace(member, roles=frozenset({tenant_role(TenantRole.ADMIN)}))
            )
            == []
        )
        assert await visible(db_session, replace(member, roles=frozenset())) == []
        assert await visible(db_session, ResourcePrincipal(None)) == []
    with tenant_context("b"):
        assert await visible(db_session, member) == []
        assert await visible(db_session, replace(member, tenant_id="b")) == []


async def test_policy_executes_one_query_for_many_resources(db_session, role_notes):
    count = []
    engine = db_session.bind.sync_engine

    def counted(*args):
        count.append(args[2])

    event.listen(engine, "before_cursor_execute", counted)
    try:
        with tenant_context("a"):
            assert (
                len(
                    await visible(
                        db_session,
                        ResourcePrincipal(
                            "friend",
                            roles=frozenset({tenant_role(TenantRole.MEMBER)}),
                            tenant_id="a",
                        ),
                    )
                )
                == 12
            )
    finally:
        event.remove(engine, "before_cursor_execute", counted)
    assert len(count) == 1
    assert "EXISTS" in count[0]


async def test_unknown_rows_grant_nothing_and_registered_custom_provider_works(
    db_session, role_notes
):
    async def unused(*args):
        return {}

    subjects = default_subject_registry()
    subjects.register(
        SubjectProvider(
            name="team",
            label_key="team.label",
            validate=unused,
            candidates=unused,
            labels=unused,
            membership=lambda who, subject_id: subject_id.in_(["one"]),
        )
    )
    with tenant_context("a"):
        share = ResourceShare(
            resource_type=NOTE_TYPE,
            resource_id=role_notes[0].id.hex,
            subject_type="team",
            subject_id="one",
            role="view",
            granted_by="owner",
        )
        db_session.add(share)
        await db_session.flush()
        who = ResourcePrincipal("friend")
        assert await visible(db_session, who) == []
        assert await visible(db_session, replace(who, context={SUBJECTS_KEY: subjects})) == [
            role_notes[0]
        ]


async def test_equal_user_and_role_ids_are_distinct_and_do_not_allow_group_self_revoke(
    db_session, role_notes
):
    from _sharing_support import FakeDirectory, register_note_type
    from sharing.contracts import ShareGrant
    from sharing.core.service import SharingError, SharingService
    from simple_module_core.access.resources import ResourceTypeRegistry

    types = ResourceTypeRegistry()
    register_note_type(types)
    service = SharingService(db_session, types, FakeDirectory("member"))
    owner_id = str(role_notes[0].owner_id)
    with tenant_context("a"):
        grant = ShareGrant(
            resource_type=NOTE_TYPE, resource_id=str(role_notes[0].id), subject_id="member"
        )
        user_share = await service.grant(ResourcePrincipal(owner_id), grant)
        shares = await service.for_resource(
            ResourcePrincipal(owner_id), NOTE_TYPE, str(role_notes[0].id)
        )
        assert {s.subject_type for s in shares} == {"user", "tenant_role"}
        role_share = next(s for s in shares if s.subject_type == "tenant_role")
        await service.revoke(ResourcePrincipal("member"), user_share.id)
        with pytest.raises(SharingError) as error:
            await service.revoke(ResourcePrincipal("member"), role_share.id)
        assert error.value.status_code == 404
