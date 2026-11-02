"""Explicit inline fallback preserves transaction ownership and error propagation."""

from unittest.mock import AsyncMock

import pytest
from simple_module_core.durable_events import DurableContext
from simple_module_core.events import EventBus
from simple_module_core.tenant_events import TenantDeleted


@pytest.mark.parametrize("transport", [False, True])
async def test_durable_or_inline_dispatch(transport):
    bus = EventBus()
    db = object()
    event = TenantDeleted("id", "slug", "Name")
    handlers = [AsyncMock(), AsyncMock()]
    for index, handler in enumerate(handlers):
        bus.subscribe_durable(TenantDeleted, handler, name=str(index))
    ordinary = AsyncMock()
    bus.subscribe(TenantDeleted, ordinary)
    if transport:
        bus.durable_transport = AsyncMock()
    await bus.publish_durable_or_inline(event, db)
    for handler in handlers:
        if transport:
            handler.assert_not_awaited()
        else:
            handler.assert_awaited_once_with(event, DurableContext(db=db, attempt=1))
    ordinary.assert_not_awaited()
    if transport:
        bus.durable_transport.enqueue.assert_awaited_once_with(event, ["0", "1"], db)


async def test_inline_failure_propagates():
    bus = EventBus()
    bus.subscribe_durable(TenantDeleted, AsyncMock(side_effect=ValueError("failed")), name="fail")
    with pytest.raises(ValueError, match="failed"):
        await bus.publish_durable_or_inline(TenantDeleted("id", "slug", "Name"), object())
