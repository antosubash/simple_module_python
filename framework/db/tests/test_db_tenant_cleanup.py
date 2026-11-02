"""Framework tenant settings teardown works independently of the UI plugin."""

from unittest.mock import AsyncMock, patch

from simple_module_core.durable_events import DurableContext
from simple_module_core.events import EventBus
from simple_module_core.tenant_events import TenantDeleted
from simple_module_db.stored_settings import SCOPE_SYSTEM, SCOPE_TENANT, SCOPE_USER, Setting
from simple_module_db.tenant_cleanup import register_tenant_cleanup
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import select

_TENANT = "deleted-tenant"
_OTHER = "retained-tenant"
_KEY = "branding.logo_file_id"


async def test_settings_cleanup_is_durable_scoped_and_idempotent():
    bus = EventBus()
    register_tenant_cleanup(bus)
    names = bus.durable.handler_names(TenantDeleted)
    assert len(names) == 1
    from simple_module_core.durable_events import event_key

    subscription = bus.durable.lookup(event_key(TenantDeleted), names[0])
    assert subscription is not None
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Setting.metadata.create_all, tables=[Setting.__table__])
        async with AsyncSession(engine) as session:
            session.add_all(
                [
                    Setting(scope=scope, scope_id=scope_id, key=_KEY, value="file-id")
                    for scope, scope_id in (
                        (SCOPE_TENANT, _TENANT),
                        (SCOPE_TENANT, _OTHER),
                        (SCOPE_USER, _TENANT),
                        (SCOPE_SYSTEM, ""),
                    )
                ]
            )
            await session.commit()
            event = TenantDeleted(tenant_id=_TENANT, slug=_TENANT, name=_TENANT)
            with patch.object(session, "commit", new_callable=AsyncMock) as commit:
                await subscription.handler(event, DurableContext(db=session, attempt=1))
                await subscription.handler(event, DurableContext(db=session, attempt=2))
                commit.assert_not_awaited()
            remaining = (await session.execute(select(Setting))).scalars().all()
            assert {(row.scope, row.scope_id) for row in remaining} == {
                (SCOPE_TENANT, _OTHER),
                (SCOPE_USER, _TENANT),
                (SCOPE_SYSTEM, ""),
            }
            await session.rollback()
            assert len((await session.execute(select(Setting))).scalars().all()) == 4
    finally:
        await engine.dispose()
