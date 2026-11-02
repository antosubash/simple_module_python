"""A durable event is delivered in the scope it was published in (GH #459).

Regression test for the delivery verification's N5: ``tenant_id`` is ``None``
both for a platform publish (inside ``all_tenants()``) and for a publish with
no tenant bound at all (a public webhook, a request before tenant resolution,
an ordinary task without a tenant). Both were delivered under
``all_tenants()``, so a publisher that could not read any tenant's data had
its handler read and write across every tenant. The scope is now recorded at
publish time and an unscoped publish is delivered unscoped and strict.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import pytest
from background_tasks.constants import OutboxScope, OutboxStatus
from background_tasks.outbox_claim import OutboxPolicy
from background_tasks.outbox_dispatch import dispatch
from file_storage.models import StoredFile
from simple_module_core import DurableContext
from simple_module_core.events import Event
from simple_module_db import (
    TenantIsolationError,
    all_tenants,
    current_tenant_id,
    finalize_session,
    tenant_context,
)
from simple_module_db.tenancy import is_all_tenants
from simple_module_db.transaction import SESSION_START_KEY
from sqlalchemy import select

pytestmark = pytest.mark.usefixtures("_stub_celery")

POLICY = OutboxPolicy(max_attempts=8, lease_seconds=300)


@dataclass
class ScopePing(Event):
    n: int


async def _publish(app, event: Event) -> None:
    async with app.state.sm.db.session_factory() as session:
        session.info[SESSION_START_KEY] = time.perf_counter()
        await app.state.sm.event_bus.publish_durable(event, session)
        await finalize_session(session)


async def _dispatch(app):
    # The dispatching task's own message carries some tenant; it must not leak.
    with tenant_context("dispatcher"):
        return await dispatch(app.state.sm.db.session_factory, app.state.sm.event_bus, POLICY)


async def test_scope_is_recorded_at_publish(app, outbox_rows):
    async def handler(event: ScopePing, ctx: DurableContext) -> None: ...

    app.state.sm.event_bus.subscribe_durable(ScopePing, handler, name="record")
    await _publish(app, ScopePing(1))
    with all_tenants():
        await _publish(app, ScopePing(2))
    with tenant_context("acme"):
        await _publish(app, ScopePing(3))

    scopes = {r.payload["n"]: (r.scope, r.tenant_id) for r in await outbox_rows()}
    assert scopes == {
        1: (OutboxScope.UNSCOPED, None),
        2: (OutboxScope.PLATFORM, None),
        3: (OutboxScope.TENANT, "acme"),
    }


async def test_each_scope_is_delivered_as_published(app):
    seen: dict[int, tuple[str | None, bool]] = {}

    async def handler(event: ScopePing, ctx: DurableContext) -> None:
        seen[event.n] = (current_tenant_id.get(), is_all_tenants())

    app.state.sm.event_bus.subscribe_durable(ScopePing, handler, name="deliver")
    await _publish(app, ScopePing(1))
    with all_tenants():
        await _publish(app, ScopePing(2))
    with tenant_context("acme"):
        await _publish(app, ScopePing(3))

    assert (await _dispatch(app)).delivered == 3
    assert seen == {1: (None, False), 2: (None, True), 3: ("acme", False)}


async def test_an_unscoped_publish_cannot_read_across_tenants(app, outbox_rows):
    async def handler(event: ScopePing, ctx: DurableContext) -> None:
        await ctx.db.execute(select(StoredFile))  # tenant-scoped: strict must refuse

    app.state.sm.event_bus.subscribe_durable(ScopePing, handler, name="unscoped-read")
    assert current_tenant_id.get() is None and not is_all_tenants()
    # The publisher itself cannot read tenant data here...
    async with app.state.sm.db.session_factory() as session:
        with pytest.raises(TenantIsolationError):
            await session.execute(select(StoredFile))
    await _publish(app, ScopePing(4))

    result = await _dispatch(app)

    # ...and neither can its handler.
    assert result.delivered == 0 and result.retrying == 1
    (row,) = await outbox_rows()
    assert row.status == OutboxStatus.PENDING
    assert "MissingTenantError" in (row.last_error or "")


async def test_a_platform_publish_can_still_read_across_tenants(app):
    async def handler(event: ScopePing, ctx: DurableContext) -> None:
        await ctx.db.execute(select(StoredFile))

    app.state.sm.event_bus.subscribe_durable(ScopePing, handler, name="platform-read")
    with all_tenants():
        await _publish(app, ScopePing(5))

    assert (await _dispatch(app)).delivered == 1
