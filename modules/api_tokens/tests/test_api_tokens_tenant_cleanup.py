"""Tenant deletion purges only the deleted tenant through a durable handler."""

from datetime import UTC, datetime, timedelta

from api_tokens.models import ApiToken
from api_tokens.module import ApiTokensModule
from simple_module_core.durable_events import DurableContext, event_key
from simple_module_core.events import EventBus
from simple_module_core.tenant_events import TenantDeleted
from simple_module_db.tenancy import all_tenants, tenant_context
from sqlmodel import select


async def test_durable_tenant_cleanup_is_scoped_idempotent_and_transactional(db_session):
    bus = EventBus()
    ApiTokensModule().register_event_handlers(bus)
    names = bus.durable.handler_names(TenantDeleted)
    assert len(names) == 1
    subscription = bus.durable.lookup(event_key(TenantDeleted), names[0])
    assert subscription is not None
    for tenant_id in ("deleted-tenant", "other-tenant"):
        with tenant_context(tenant_id):
            db_session.add(
                ApiToken(
                    name="token",
                    prefix="test",
                    token_hash=tenant_id,
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
            await db_session.flush()
    await db_session.commit()
    event = TenantDeleted(tenant_id="deleted-tenant", slug="deleted", name="Deleted")
    ctx = DurableContext(db=db_session, attempt=1)
    # A worker rollback must restore rows: the handler must never commit its session.
    await subscription.handler(event, ctx)
    await db_session.rollback()
    with all_tenants():
        assert len((await db_session.execute(select(ApiToken))).scalars().all()) == 2
    await subscription.handler(event, ctx)
    await subscription.handler(event, DurableContext(db=db_session, attempt=2))
    with all_tenants():
        remaining = (await db_session.execute(select(ApiToken))).scalars().all()
    assert [row.tenant_id for row in remaining] == ["other-tenant"]
