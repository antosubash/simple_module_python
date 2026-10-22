"""Deleting the tenant and enqueueing its teardown are one transaction."""

import pytest
from background_tasks.models import OutboxMessage
from simple_module_core.durable_events import DurableDeliveryUnavailable, event_key
from simple_module_core.events import EventBus
from simple_module_core.tenant_events import TenantDeleted
from simple_module_db.transaction import finalize_session, rollback_session
from sqlalchemy import select
from tenants.contracts.events import TenantDeleted as ProviderTenantDeleted
from tenants.models import Tenant
from tenants.service import TenantService
from tenants_deletion_helpers import deletion_bus


async def _cleanup(event, ctx):
    pass


async def test_tenants_delete_enqueues_before_commit(db_session):
    bus = deletion_bus()
    bus.subscribe_durable(TenantDeleted, _cleanup, name="test.cleanup")
    tenant = Tenant(id="durable", slug="durable", name="Durable")
    db_session.add(tenant)
    await finalize_session(db_session)

    await TenantService(db_session, bus=bus).delete_tenant(tenant.id)
    rows = (await db_session.execute(select(OutboxMessage))).scalars().all()
    assert len(rows) == 1
    assert rows[0].payload == {"tenant_id": "durable", "slug": "durable", "name": "Durable"}
    assert rows[0].event_key == event_key(TenantDeleted)
    assert rows[0].handler_name == "test.cleanup"
    assert ProviderTenantDeleted is TenantDeleted

    await rollback_session(db_session)
    assert (await db_session.execute(select(OutboxMessage))).scalars().all() == []
    assert await db_session.get(Tenant, "durable") is not None


@pytest.mark.parametrize("bus", [None, EventBus()], ids=["no-bus", "no-transport"])
async def test_tenants_delete_requires_durable_transport(db_session, bus):
    tenant = Tenant(id="durable", slug="durable", name="Durable")
    db_session.add(tenant)
    await finalize_session(db_session)
    with pytest.raises(DurableDeliveryUnavailable):
        await TenantService(db_session, bus=bus).delete_tenant(tenant.id)
    await rollback_session(db_session)
    assert await db_session.get(Tenant, "durable") is not None
