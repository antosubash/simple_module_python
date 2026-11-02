"""User lifecycle events and cross-module cleanup are transactional (#627)."""

import uuid

import pytest
from background_tasks.models import OutboxMessage
from background_tasks.outbox_transport import _OutboxWriter
from permissions.models import UserPermission
from permissions.module import PermissionsModule
from sharing.constants import SUBJECT_USER
from sharing.models import ResourceShare
from sharing.module import SharingModule
from simple_module_core.durable_events import event_key
from simple_module_core.events import EventBus
from simple_module_db import all_tenants, tenant_context
from simple_module_db.transaction import finalize_session, rollback_session
from sqlmodel import select
from starlette.requests import Request
from tenants.constants import MembershipRole, TenantStatus
from tenants.models import Membership, Tenant
from tenants.module import TenantsModule
from tenants.service import TenantService
from users.admin.api import admin_delete_user, admin_disable_user, admin_set_roles
from users.admin.service import UserService
from users.contracts.events import RoleAssigned, UserDeleted, UserDisabled
from users.contracts.schemas import RoleAssignment
from users.models import Role, User, UserRole


class PausedUserTransport(_OutboxWriter):
    def schedule(self, db, ids):
        pass


async def record_user_event(event, ctx):
    pass


def cleanup_bus(durable=False):
    bus = EventBus()
    for module in (TenantsModule(), SharingModule(), PermissionsModule()):
        module.register_event_handlers(bus)
    if durable:
        bus.durable_transport = PausedUserTransport()
    return bus


def request():
    return Request({"type": "http"})


async def seed_cleanup(db, user_id, other_id):
    db.add(User(id=user_id, email="deleted@example.com", hashed_password="unused"))
    for tenant_id in ("sole", "coowned", "unrelated"):
        db.add(Tenant(id=tenant_id, slug=tenant_id, name=tenant_id))
    await db.flush()
    for tenant_id in ("sole", "coowned"):
        db.add(
            Membership(
                tenant_id=tenant_id,
                user_id=str(user_id),
                role=MembershipRole.OWNER,
                email="deleted@example.com",
            )
        )
    for tenant_id in ("coowned", "unrelated"):
        db.add(Membership(tenant_id=tenant_id, user_id=str(other_id), role=MembershipRole.OWNER))
    for tenant_id in ("sole", "coowned"):
        with tenant_context(tenant_id):
            for subject_id in (str(user_id), str(other_id)):
                db.add(
                    ResourceShare(
                        resource_type="test.note",
                        resource_id="1",
                        subject_type=SUBJECT_USER,
                        subject_id=subject_id,
                        role="view",
                        granted_by=str(other_id),
                    )
                )
            await db.flush()
    for uid in (user_id, other_id):
        db.add(UserPermission(user_id=uid, permission_key="test.view"))
    await finalize_session(db)


@pytest.mark.parametrize("rollback", [False, True])
async def test_user_deleted_purges_all_tenants_and_grants(db_session, rollback):
    user_id, other_id = uuid.uuid4(), uuid.uuid4()
    await seed_cleanup(db_session, user_id, other_id)
    bus = cleanup_bus()
    # A deletion made while acting in one tenant must still clean every tenant.
    with tenant_context("sole"):
        await admin_delete_user(user_id, request(), bus, UserService(db_session, None), db_session)
    assert not await TenantService(db_session).has_member_email("sole", "deleted@example.com")
    assert (await db_session.get(Tenant, "sole")).status == TenantStatus.SUSPENDED
    assert (await db_session.get(Tenant, "coowned")).status == TenantStatus.ACTIVE
    assert (await db_session.get(Tenant, "unrelated")).status == TenantStatus.ACTIVE
    with all_tenants():
        shares = (await db_session.execute(select(ResourceShare))).scalars().all()
    assert len(shares) == 2
    assert {s.subject_id for s in shares} == {str(other_id)}
    assert (await db_session.execute(select(UserPermission.user_id))).scalars().all() == [other_id]
    # Re-delivery is harmless, including when the user no longer exists.
    await bus.publish_durable_or_inline(UserDeleted(user_id), db_session)
    if rollback:
        await rollback_session(db_session)
        assert await db_session.get(User, user_id) is not None
        assert (await db_session.get(Tenant, "sole")).status == TenantStatus.ACTIVE
        assert len((await db_session.execute(select(Membership))).scalars().all()) == 4
        with all_tenants():
            assert len((await db_session.execute(select(ResourceShare))).scalars().all()) == 4
        assert len((await db_session.execute(select(UserPermission))).scalars().all()) == 2
    else:
        await finalize_session(db_session)
        assert await db_session.get(User, user_id) is None


@pytest.mark.parametrize(
    "operation,event_type",
    [("delete", UserDeleted), ("disable", UserDisabled), ("roles", RoleAssigned)],
)
async def test_admin_events_outbox_rolls_back_with_user_write(db_session, operation, event_type):
    uid = uuid.uuid4()
    db_session.add(User(id=uid, email="events@example.com", hashed_password="unused"))
    db_session.add(Role(name="new-role"))
    await finalize_session(db_session)
    bus = cleanup_bus(durable=True)
    bus.subscribe_durable(event_type, record_user_event)
    observed = []

    async def observe(event):
        observed.append(event)

    bus.subscribe(event_type, observe)
    service = UserService(db_session, None)
    if operation == "delete":
        await admin_delete_user(uid, request(), bus, service, db_session)
    elif operation == "disable":
        await admin_disable_user(uid, bus, service, db_session)
    else:
        await admin_set_roles(
            uid, RoleAssignment(role_names=["new-role"]), request(), bus, service, db_session
        )
    rows = (await db_session.execute(select(OutboxMessage))).scalars().all()
    assert rows
    assert {row.event_key for row in rows} == {event_key(event_type)}
    assert observed == []
    await rollback_session(db_session)
    assert (await db_session.execute(select(OutboxMessage))).scalars().all() == []
    user = await db_session.get(User, uid)
    assert user is not None and user.is_active
    assert (await db_session.execute(select(UserRole))).scalars().all() == []
    assert observed == []


async def test_role_assigned_only_for_new_resolved_roles(db_session):
    uid = uuid.uuid4()
    user = User(id=uid, email="roles@example.com", hashed_password="unused")
    held, added = Role(name="held"), Role(name="added")
    db_session.add_all([user, held, added])
    await db_session.flush()
    db_session.add(UserRole(user_id=uid, role_id=held.id))
    await finalize_session(db_session)
    bus = EventBus()
    bus.durable_transport = PausedUserTransport()
    bus.subscribe_durable(RoleAssigned, record_user_event)
    for _ in range(2):
        await admin_set_roles(
            uid,
            RoleAssignment(role_names=["held", "added", "added", "missing"]),
            request(),
            bus,
            UserService(db_session, None),
            db_session,
        )
    rows = (await db_session.execute(select(OutboxMessage))).scalars().all()
    assert [row.payload["role_name"] for row in rows] == ["added"]


async def test_ordinary_user_events_wait_for_commit(db_session):
    from users.admin.events import publish_admin_event

    bus = EventBus()
    observed = []

    async def observe(event):
        observed.append(event.user_id)

    bus.subscribe(UserDisabled, observe)
    uid = uuid.uuid4()
    db_session.add(User(id=uid, email="committed@example.com", hashed_password="unused"))
    await publish_admin_event(bus, UserDisabled(uid), db_session)
    assert observed == []
    await finalize_session(db_session)
    assert observed == [uid]
