"""Tenant deletion purges tenant overrides without touching other scopes."""

from feature_flags.constants import SCOPE_SYSTEM, SCOPE_TENANT
from feature_flags.models import FeatureFlagOverride
from feature_flags.module import FeatureFlagsModule
from simple_module_core.durable_events import DurableContext, event_key
from simple_module_core.events import EventBus
from simple_module_core.tenant_events import TenantDeleted
from sqlmodel import select


async def test_durable_tenant_cleanup_is_scoped_idempotent_and_transactional(db_session):
    bus = EventBus()
    FeatureFlagsModule().register_event_handlers(bus)
    names = bus.durable.handler_names(TenantDeleted)
    assert len(names) == 1
    subscription = bus.durable.lookup(event_key(TenantDeleted), names[0])
    assert subscription is not None
    scopes = [(SCOPE_TENANT, "deleted"), (SCOPE_TENANT, "other"), (SCOPE_SYSTEM, "deleted")]
    for scope, scope_id in scopes:
        db_session.add(FeatureFlagOverride(scope=scope, scope_id=scope_id, name="test.flag"))
    await db_session.commit()
    event = TenantDeleted(tenant_id="deleted", slug="deleted", name="Deleted")
    ctx = DurableContext(db=db_session, attempt=1)
    await subscription.handler(event, ctx)
    await db_session.rollback()
    assert len((await db_session.execute(select(FeatureFlagOverride))).scalars().all()) == 3
    await subscription.handler(event, ctx)
    await subscription.handler(event, DurableContext(db=db_session, attempt=2))
    rows = (await db_session.execute(select(FeatureFlagOverride))).scalars().all()
    assert {(row.scope, row.scope_id) for row in rows} == {
        (SCOPE_TENANT, "other"),
        (SCOPE_SYSTEM, "deleted"),
    }
