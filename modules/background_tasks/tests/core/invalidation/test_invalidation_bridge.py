"""The temporary bridge must work in both directions of a rolling upgrade."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from background_tasks.core.invalidation import RedisInvalidationTransport
from simple_module_core.invalidation import Invalidation, InvalidationBus
from simple_module_test import wait_for


async def test_bridge_publishes_and_receives_on_both_channels(monkeypatch):
    channels = []
    frames = asyncio.Queue()

    async def subscribe(*names):
        channels.extend(names)

    async def get_message(**kwargs):
        return await frames.get()

    pubsub = SimpleNamespace(subscribe=subscribe, get_message=get_message, aclose=AsyncMock())
    client = SimpleNamespace(
        pubsub=lambda: pubsub, ping=AsyncMock(), publish=AsyncMock(), aclose=AsyncMock()
    )
    monkeypatch.setattr("redis.asyncio.from_url", lambda *args, **kwargs: client)
    bus = InvalidationBus()
    seen = []
    bus.subscribe("cache", seen.append)
    transport = RedisInvalidationTransport(
        bus,
        "redis://fake",
        "simple_module.invalidation.app",
        legacy_channel="simple_module.invalidation",
    )
    await transport.start()
    try:
        await wait_for(lambda: bool(channels))
        assert channels == ["simple_module.invalidation.app", "simple_module.invalidation"]
        # An old process publishes only on the global channel; a new one uses the derived one.
        for channel, key in zip(channels, ("from-new", "from-old"), strict=True):
            message = Invalidation(channel="cache", key=key, origin="another-process").to_wire()
            await frames.put({"type": "message", "channel": channel, "data": message})
        await wait_for(lambda: len(seen) == 2)
        assert [message.key for message in seen] == ["from-new", "from-old"]
        await transport.publish("payload")
        assert [call.args for call in client.publish.call_args_list] == [
            ("simple_module.invalidation.app", "payload"),
            ("simple_module.invalidation", "payload"),
        ]
    finally:
        await transport.stop()


async def test_new_publish_is_dispatched_once_across_the_bridge(monkeypatch):
    frames = asyncio.Queue()
    subscribed = asyncio.Event()

    async def subscribe(*channels):
        subscribed.set()

    async def get_message(**kwargs):
        return await frames.get()

    async def publish(channel, message):
        await frames.put({"type": "message", "channel": channel, "data": message.encode()})

    pubsub = SimpleNamespace(subscribe=subscribe, get_message=get_message, aclose=AsyncMock())
    client = SimpleNamespace(
        pubsub=lambda: pubsub, ping=AsyncMock(), publish=publish, aclose=AsyncMock()
    )
    monkeypatch.setattr("redis.asyncio.from_url", lambda *a, **kw: client)
    receiver = InvalidationBus(origin="receiver")
    sender = InvalidationBus(origin="sender")
    seen = []
    drained = asyncio.Event()
    receiver.subscribe("cache", seen.append)
    receiver.subscribe("sentinel", lambda message: drained.set())
    transport = RedisInvalidationTransport(
        receiver, "redis://fake", "installation-channel", legacy_channel="legacy-channel"
    )
    sender.set_transport(transport)
    await transport.start()
    try:
        await subscribed.wait()
        await sender.publish("cache", "same-key")
        await sender.publish("cache", "same-key")
        await sender.publish("sentinel")
        await drained.wait()
        assert [message.key for message in seen] == ["same-key", "same-key"]
    finally:
        await transport.stop()
