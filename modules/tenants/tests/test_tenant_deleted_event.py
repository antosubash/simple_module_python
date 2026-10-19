"""``TenantService.delete_tenant`` publishes ``TenantDeleted`` after commit only."""

from __future__ import annotations

from simple_module_core.events import EventBus
from simple_module_db.transaction import finalize_session, rollback_session
from sqlalchemy import func, select
from tenants.contracts.events import TenantDeleted
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
