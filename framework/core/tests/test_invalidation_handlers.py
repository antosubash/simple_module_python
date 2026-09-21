"""Handler-registration hazards, split from ``test_invalidation.py``.

That file asks whether the bus delivers the right message to the right handler;
this one asks what happens when the set of handlers changes while the bus is
walking it. Different question, and together they crossed the 300-line cap.
"""

from __future__ import annotations

import asyncio

from simple_module_core.invalidation import InvalidationBus


class TestReentrantSubscribe:
    """A handler that subscribes during dispatch must not wedge the event loop.

    ``_dispatch`` used to iterate the live handler list, so a handler that
    re-armed itself appended to the list being walked. With sync handlers that
    loop has no await point, so it did not merely recurse — it took the event
    loop with it, and neither ``asyncio.timeout`` nor the per-handler ``except``
    could intervene. Found by exploratory QA at 3.1 million invocations from one
    ``publish``; the fix is to iterate a snapshot.
    """

    async def test_a_self_rearming_handler_terminates(self):
        bus = InvalidationBus()
        calls: list[int] = []

        def rearm(inv):
            calls.append(1)
            bus.subscribe("orders.totals", rearm)

        bus.subscribe("orders.totals", rearm)

        # A real timeout, because the failure mode is a hang rather than a wrong
        # answer. It can only fire if the loop yields, which is exactly what the
        # bug prevented — so on a regression this test times out and fails.
        async with asyncio.timeout(10):
            await bus.publish("orders.totals", key="k")

        assert calls == [1], "the handler ran more than once within a single publish"

    async def test_a_handler_added_during_dispatch_waits_for_the_next_publish(self):
        """The snapshot's other consequence, stated so it is not a surprise."""
        bus = InvalidationBus()
        calls: list[str] = []

        def adder(inv):
            calls.append("adder")
            bus.subscribe("c", lambda i: calls.append("added"))

        bus.subscribe("c", adder)

        async with asyncio.timeout(10):
            await bus.publish("c")
        assert calls == ["adder"]

        calls.clear()
        async with asyncio.timeout(10):
            await bus.publish("c")
        assert "added" in calls
