"""``TenantService.delete_tenant`` publishes its events and invalidates after commit only."""

from __future__ import annotations

import pytest
from simple_module_core.events import EventBus
from simple_module_db.transaction import finalize_session, rollback_session
from sqlalchemy import func, select
from tenants import resolver
from tenants.constants import MembershipRole
from tenants.contracts.events import MembershipRemoved, TenantDeleted
from tenants.contracts.schemas import TenantCreate
from tenants.models import Membership, Tenant
from tenants.service import TenantService


async def _tenant_with_owner(db_session, bus: EventBus) -> tuple[TenantService, Tenant]:
    svc = TenantService(db_session, bus=bus)
    tenant = await svc.create_tenant(TenantCreate(name="Acme"), owner_user_id="u1")
    await finalize_session(db_session)
    return svc, tenant


async def test_delete_publishes_after_commit(db_session):
    bus = EventBus()
    seen: list[TenantDeleted] = []

    async def handler(event: TenantDeleted) -> None:
        # The delete is already durable when the handler runs.
        assert await db_session.get(Tenant, event.tenant_id) is None
        seen.append(event)

    bus.subscribe(TenantDeleted, handler)
    svc, tenant = await _tenant_with_owner(db_session, bus)

    await svc.delete_tenant(tenant.id)
    assert seen == []  # nothing before the commit

    await finalize_session(db_session)
    assert seen == [TenantDeleted(tenant.id, "acme", "Acme")]
    members = await db_session.scalar(select(func.count()).select_from(Membership))
    assert members == 0


async def test_rolled_back_delete_publishes_nothing(db_session):
    bus = EventBus()
    seen: list[TenantDeleted] = []

    async def handler(event: TenantDeleted) -> None:
        seen.append(event)

    bus.subscribe(TenantDeleted, handler)
    svc, tenant = await _tenant_with_owner(db_session, bus)

    await svc.delete_tenant(tenant.id)
    await rollback_session(db_session)

    assert seen == []
    remaining = await db_session.scalar(select(func.count()).select_from(Tenant))
    assert remaining == 1


@pytest.fixture(autouse=True)
def _clear_membership_cache():
    yield
    resolver.forget(None)


async def _tenant_with_members(db_session, bus: EventBus, invalidated: list[str | None]):
    async def invalidate(key: str | None) -> None:
        resolver.forget(key)
        invalidated.append(key)

    svc = TenantService(db_session, bus=bus, invalidate=invalidate)
    tenant = await svc.create_tenant(TenantCreate(name="Acme"), owner_user_id="u1")
    await svc.add_member(tenant.id, "u2", MembershipRole.MEMBER)
    await finalize_session(db_session)
    invalidated.clear()
    for user_id in ("u1", "u2"):  # both members' tenant lists are cached
        resolver._MEMBERSHIPS[user_id] = []
    return svc, tenant


async def test_delete_removes_every_member_after_commit(db_session):
    bus = EventBus()
    removed: list[MembershipRemoved] = []

    async def handler(event: MembershipRemoved) -> None:
        removed.append(event)

    bus.subscribe(MembershipRemoved, handler)
    invalidated: list[str | None] = []
    svc, tenant = await _tenant_with_members(db_session, bus, invalidated)

    await svc.delete_tenant(tenant.id)
    assert removed == [] and invalidated == []  # nothing before the commit
    assert resolver.cached_memberships("u2") is not None

    await finalize_session(db_session)
    assert sorted(removed, key=lambda e: e.user_id) == [
        MembershipRemoved(tenant.id, "u1"),
        MembershipRemoved(tenant.id, "u2"),
    ]
    assert invalidated == [None]  # one broadcast drops every worker's cache
    assert resolver.cached_memberships("u1") is None
    assert resolver.cached_memberships("u2") is None


async def test_rolled_back_delete_removes_no_member(db_session):
    bus = EventBus()
    removed: list[MembershipRemoved] = []

    async def handler(event: MembershipRemoved) -> None:
        removed.append(event)

    bus.subscribe(MembershipRemoved, handler)
    invalidated: list[str | None] = []
    svc, tenant = await _tenant_with_members(db_session, bus, invalidated)

    await svc.delete_tenant(tenant.id)
    await rollback_session(db_session)

    assert removed == [] and invalidated == []
    assert resolver.cached_memberships("u2") is not None
    members = await db_session.scalar(select(func.count()).select_from(Membership))
    assert members == 2
