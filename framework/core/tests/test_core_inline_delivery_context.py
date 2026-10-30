"""Inline durable dispatch marks its handlers as in-delivery (#682)."""

from simple_module_core.durable_events import in_delivery
from simple_module_core.events import EventBus
from simple_module_core.tenant_events import TenantDeleted


async def test_inline_durable_handler_sees_in_delivery():
    bus = EventBus()
    seen: list[bool] = []

    async def handler(event, ctx):
        seen.append(in_delivery())

    bus.subscribe_durable(TenantDeleted, handler, name="probe")
    assert in_delivery() is False
    await bus.publish_durable_or_inline(TenantDeleted("id", "slug", "Name"), object())
    assert seen == [True]
    assert in_delivery() is False
