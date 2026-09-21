"""The transport against a real ``redis-server``, not the fake.

``test_bg_invalidation.py`` proves this repo's own logic — retry, timeout,
teardown — against a fake client. It cannot prove that redis-py does what the
fake pretends: that ``pubsub().listen()`` yields frames shaped
``{"type": "message", "data": ...}``, that ``data`` arrives as ``bytes``, that
``from_url`` accepts ``socket_connect_timeout``, that ``aclose`` exists on both
the client and the pubsub. The transport wraps its teardown in
``contextlib.suppress(Exception)``, so a wrong method name there would be
silently swallowed and nothing in the fake-based suite would notice.

These tests are the answer to that. They need no ``docker-up``: the
``redis_server`` fixture starts its own ephemeral server. The cases where the
broker is *not* working live in ``test_bg_invalidation_degraded.py``.
"""

from __future__ import annotations

import asyncio

import pytest
from background_tasks.invalidation import RedisInvalidationTransport
from simple_module_core.invalidation import Invalidation, InvalidationBus

_CHANNEL = "qa.invalidation"
_DELIVERY_TIMEOUT_SECONDS = 5.0


async def _await_delivery(seen: list[Invalidation], count: int = 1) -> None:
    """Wait for the listener task to have delivered *count* messages.

    Polling rather than a fixed sleep: a subscription round trip over loopback is
    sub-millisecond in practice but a loaded CI runner is not, and a sleep long
    enough to be safe there would be a second added to every run.
    """
    deadline = asyncio.get_running_loop().time() + _DELIVERY_TIMEOUT_SECONDS
    while len(seen) < count:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"delivered {len(seen)} of {count} messages before timing out")
        await asyncio.sleep(0.01)


async def _subscribed(bus: InvalidationBus, url: str, channel: str = _CHANNEL):
    """A started transport whose listener has actually subscribed.

    ``start`` returns before the listener's first ``subscribe`` completes — by
    design, since an unreachable broker must not fail a boot — so a test that
    published immediately would race the subscription and lose the message. Redis
    pub/sub has no replay: a message published to a channel with no subscriber is
    dropped, not queued. So this polls ``PUBSUB NUMSUB`` until the server itself
    reports the subscriber.
    """
    transport = RedisInvalidationTransport(bus, url, channel)
    await transport.start()

    import redis.asyncio as aioredis

    probe = aioredis.from_url(url)
    try:
        deadline = asyncio.get_running_loop().time() + _DELIVERY_TIMEOUT_SECONDS
        while True:
            counts = await probe.pubsub_numsub(channel)
            if counts and counts[0][1] >= 1:
                return transport
            if asyncio.get_running_loop().time() > deadline:
                await transport.stop()
                raise AssertionError(f"listener never subscribed to {channel!r}")
            await asyncio.sleep(0.01)
    finally:
        await probe.aclose()


class TestRealRoundTrip:
    async def test_a_published_invalidation_comes_back_through_the_bus(self, redis_server):
        """The whole transport, over a real socket: publish here, deliver there."""
        publisher = InvalidationBus()
        receiver = InvalidationBus()
        seen: list[Invalidation] = []
        receiver.subscribe(_CHANNEL, seen.append)

        listener = await _subscribed(receiver, redis_server)
        sender = RedisInvalidationTransport(publisher, redis_server, _CHANNEL)
        await sender.start()
        publisher.set_transport(sender)
        try:
            await publisher.publish(_CHANNEL, key="user-1")
            await _await_delivery(seen)
        finally:
            await sender.stop()
            await listener.stop()

        assert [(i.channel, i.key) for i in seen] == [(_CHANNEL, "user-1")]
        assert seen[0].origin == publisher.origin, "the receiver must see who sent it"

    async def test_redis_delivers_data_as_bytes_the_bus_can_decode(self, redis_server):
        """Pins the assumption the fake encodes: ``data`` is bytes, and decodable.

        If redis-py ever handed back ``str`` or a memoryview, ``from_wire`` would
        still cope — but a test that says so is the difference between coping by
        design and coping by luck.
        """
        bus = InvalidationBus()
        raw: list[object] = []

        async def capture(message):
            raw.append(message)

        bus.deliver = capture  # type: ignore[method-assign]

        listener = await _subscribed(bus, redis_server)
        import redis.asyncio as aioredis

        client = aioredis.from_url(redis_server)
        try:
            await client.publish(_CHANNEL, Invalidation(channel=_CHANNEL, key="k").to_wire())
            deadline = asyncio.get_running_loop().time() + _DELIVERY_TIMEOUT_SECONDS
            while not raw and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.01)
        finally:
            await client.aclose()
            await listener.stop()

        assert raw, "nothing reached the bus"
        assert isinstance(raw[0], bytes)
        assert Invalidation.from_wire(raw[0]) is not None


class TestOriginFilterAcrossTheWire:
    async def test_the_publisher_does_not_reapply_its_own_broadcast(self, redis_server):
        """The origin filter, end to end — the echo a real subscription receives.

        A publisher that subscribes to its own channel gets its own message back
        off the socket. ``publish`` already ran the handlers locally, so applying
        the echo would run them twice; this proves the filter catches a real
        round trip, not just a hand-built one.
        """
        bus = InvalidationBus()
        seen: list[Invalidation] = []
        bus.subscribe(_CHANNEL, seen.append)

        transport = await _subscribed(bus, redis_server)
        bus.set_transport(transport)
        try:
            await bus.publish(_CHANNEL, key="once")
            # Give the echo time to arrive and be rejected. There is no
            # positive signal for "a message was correctly ignored", so this
            # waits out the delivery window instead of polling for one.
            await asyncio.sleep(0.3)
        finally:
            await transport.stop()

        assert len(seen) == 1, "the publisher applied its own echo a second time"

    async def test_a_second_worker_does_apply_it(self, redis_server):
        """The same message, to a bus that did not publish it — must apply."""
        publisher = InvalidationBus()
        other = InvalidationBus()
        seen: list[Invalidation] = []
        other.subscribe(_CHANNEL, seen.append)

        listener = await _subscribed(other, redis_server)
        sender = RedisInvalidationTransport(publisher, redis_server, _CHANNEL)
        await sender.start()
        publisher.set_transport(sender)
        try:
            await publisher.publish(_CHANNEL, key="u")
            await _await_delivery(seen)
        finally:
            await sender.stop()
            await listener.stop()

        assert [i.key for i in seen] == ["u"]


class TestChannelIsolation:
    async def test_only_the_configured_channel_is_subscribed(self, redis_server):
        """A message on another channel must not reach this transport's bus.

        Two apps on one Redis *server* is the case
        ``SM_BG_TASKS_INVALIDATION_CHANNEL`` exists for — pub/sub ignores the
        logical database index, so a different DB number is no isolation at all
        and the channel name is the only thing separating two installs. If the
        setting were ignored, renaming it would do nothing and each app would act
        on the other's traffic.
        """
        bus = InvalidationBus()
        seen: list[Invalidation] = []
        bus.subscribe(_CHANNEL, seen.append)

        transport = await _subscribed(bus, redis_server, "app-one.invalidation")
        import redis.asyncio as aioredis

        client = aioredis.from_url(redis_server)
        try:
            wire = Invalidation(channel=_CHANNEL, key="k", origin="elsewhere").to_wire()
            await client.publish("app-two.invalidation", wire)
            await asyncio.sleep(0.3)
        finally:
            await client.aclose()
            await transport.stop()

        assert seen == []


class TestTeardown:
    async def test_stop_releases_the_subscription_on_the_server(self, redis_server):
        """``aclose`` on the client and the pubsub really close them.

        The transport suppresses exceptions while tearing down, so a renamed or
        missing method would leak a connection silently and only show up as a
        server running out of clients. Asserted against the server's own
        subscriber count rather than the object's state.
        """
        bus = InvalidationBus()
        transport = await _subscribed(bus, redis_server)
        await transport.stop()

        import redis.asyncio as aioredis

        probe = aioredis.from_url(redis_server)
        try:
            deadline = asyncio.get_running_loop().time() + _DELIVERY_TIMEOUT_SECONDS
            while True:
                counts = await probe.pubsub_numsub(_CHANNEL)
                if not counts or counts[0][1] == 0:
                    break
                if asyncio.get_running_loop().time() > deadline:
                    raise AssertionError("the subscription outlived stop()")
                await asyncio.sleep(0.05)
        finally:
            await probe.aclose()

    async def test_publish_after_stop_does_not_hang(self, redis_server):
        """A publish on a stopped transport fails fast rather than blocking."""
        bus = InvalidationBus()
        transport = RedisInvalidationTransport(bus, redis_server, _CHANNEL)
        await transport.start()
        await transport.stop()

        with pytest.raises(Exception):  # noqa: B017 — any failure, just not a hang
            await asyncio.wait_for(transport.publish("{}"), timeout=5)
