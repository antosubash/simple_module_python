"""Bridge copies run handlers once; independent and legacy invalidations still run."""

import asyncio
import json

import pytest
from simple_module_core.eventing.invalidation import InvalidationBus


class RecordingTransport:
    def __init__(self):
        self.sent = []

    async def publish(self, message):
        self.sent.append(message)


async def test_bridge_copies_deliver_once_but_repeated_publishes_each_deliver():
    sender = InvalidationBus(origin="sender")
    receiver = InvalidationBus(origin="receiver")
    transport = RecordingTransport()
    sender.set_transport(transport)
    seen = []
    receiver.subscribe("cache", seen.append)

    for _ in range(2):
        await sender.publish("cache", "same-key")
        frame = transport.sent[-1]
        await receiver.deliver(frame)
        await receiver.deliver(frame.encode())

    assert [message.key for message in seen] == ["same-key", "same-key"]
    ids = [json.loads(frame)["id"] for frame in transport.sent]
    assert ids[0] and ids[0] != ids[1]


async def test_legacy_frames_without_ids_are_not_deduplicated():
    bus = InvalidationBus()
    seen = []
    bus.subscribe("cache", seen.append)
    frame = json.dumps({"v": 1, "channel": "cache", "key": "k", "origin": "old"})
    await bus.deliver(frame)
    await bus.deliver(frame)
    assert len(seen) == 2


async def test_duplicate_is_ignored_while_an_async_handler_is_running():
    bus = InvalidationBus()
    entered = asyncio.Event()
    release = asyncio.Event()
    seen = []

    async def handler(message):
        seen.append(message)
        entered.set()
        await release.wait()

    bus.subscribe("cache", handler)
    frame = json.dumps({"v": 1, "channel": "cache", "id": "same-id", "origin": "other"})
    first = asyncio.create_task(bus.deliver(frame))
    try:
        await entered.wait()
        async with asyncio.timeout(1):
            await bus.deliver(frame)
        assert len(seen) == 1
    finally:
        release.set()
        await first


async def test_recent_id_storage_is_bounded_and_preserves_newer_entries():
    from simple_module_core.eventing.invalidation import RECENT_MESSAGE_LIMIT

    bus = InvalidationBus()
    seen = []
    bus.subscribe("cache", seen.append)

    def frame(index):
        return json.dumps({"v": 1, "channel": "cache", "id": str(index), "origin": "other"})

    for index in range(RECENT_MESSAGE_LIMIT + 1):
        await bus.deliver(frame(index))
    await bus.deliver(frame(RECENT_MESSAGE_LIMIT))
    assert len(seen) == RECENT_MESSAGE_LIMIT + 1
    await bus.deliver(frame(0))
    assert len(seen) == RECENT_MESSAGE_LIMIT + 2


@pytest.mark.parametrize("message_id", [[], {}, 12])
async def test_malformed_id_is_ignored_without_breaking_later_delivery(message_id):
    bus = InvalidationBus()
    seen = []
    bus.subscribe("cache", seen.append)
    frame = {"v": 1, "channel": "cache", "origin": "other", "id": message_id}
    await bus.deliver(json.dumps(frame))
    frame["id"] = "valid-id"
    await bus.deliver(json.dumps(frame))
    assert len(seen) == 1
