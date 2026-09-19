"""The transport when the broker is down, or up and mute.

Split from ``test_bg_invalidation_redis.py`` — that file asks whether a working
Redis round trip works, these ask what happens when it does not, which needs no
Redis at all and a different set of fixtures. Keeping them together pushed the
file past the 300-line cap.

The distinction between the two cases here is the whole point. A *refused*
connection fails instantly and proves nothing about any timeout. A broker that
accepts the connection and then answers nothing is the failure mode the publish
timeout exists for, and the one that would otherwise hang a password change
inside its own response cycle.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket

from background_tasks.invalidation import RedisInvalidationTransport
from simple_module_core.invalidation import Invalidation, InvalidationBus

_CHANNEL = "qa.invalidation"


def _unused_url() -> str:
    """A loopback port nothing is listening on — connections are refused at once."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    return f"redis://127.0.0.1:{port}/0"


class TestUnreachableBroker:
    """A broker that is down, and the nastier case of one that is *up and mute*."""

    async def test_a_refused_connection_never_breaks_the_local_effect(self):
        """Nothing listening: the publish fails, the eviction still happens.

        Note what this does and does not prove. A refused connection fails
        immediately, so this passes with or without a connect timeout — it is a
        test of the bus swallowing the error, not of the timeout. The timeout is
        what :meth:`test_a_mute_broker_is_bounded_by_the_publish_timeout` covers.
        """
        bus = InvalidationBus()
        seen: list[Invalidation] = []
        bus.subscribe(_CHANNEL, seen.append)
        transport = RedisInvalidationTransport(bus, _unused_url(), _CHANNEL)
        await transport.start()
        bus.set_transport(transport)
        try:
            await asyncio.wait_for(bus.publish(_CHANNEL, key="k"), timeout=20)
        finally:
            await transport.stop()

        assert [i.key for i in seen] == ["k"]

    async def test_a_mute_broker_is_bounded_by_the_publish_timeout(self, monkeypatch):
        """A server that accepts the connection and then says nothing.

        This is the failure mode with teeth, and the reason the publish carries
        its own ``asyncio.timeout``. ``socket_connect_timeout`` does not help
        here — the connect succeeds — and redis-py has no *command* timeout by
        default, so the ``PUBLISH`` would wait forever. It runs inside the
        response cycle of the request that made the write, so "forever" means a
        hung password change.

        A command timeout cannot simply be set on the client instead: the same
        connection pool serves ``pubsub.listen()``, which is *supposed* to block
        indefinitely, and a socket timeout would tear the subscription down.
        Hence the bound lives on the publish call.
        """
        import background_tasks.invalidation as bg_invalidation

        # The handler must *hold* the connection open and answer nothing — that
        # is what "mute" means. It must also be closable from here: a socket the
        # redis client still owns keeps ``Server.wait_closed()`` waiting forever
        # on 3.12+, which hangs the teardown rather than the code under test.
        writers: list[asyncio.StreamWriter] = []

        async def hold(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writers.append(writer)
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.Event().wait()

        server = await asyncio.start_server(hold, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(bg_invalidation, "PUBLISH_TIMEOUT_SECONDS", 0.25)

        bus = InvalidationBus()
        seen: list[Invalidation] = []
        bus.subscribe(_CHANNEL, seen.append)
        transport = RedisInvalidationTransport(bus, f"redis://127.0.0.1:{port}/0", _CHANNEL)
        await transport.start()
        bus.set_transport(transport)
        try:
            # wait_for well over the 0.25s bound but well under any plausible
            # hang: if the publish were unbounded this raises here and fails.
            await asyncio.wait_for(bus.publish(_CHANNEL, key="k"), timeout=10)
        finally:
            await transport.stop()
            for writer in writers:
                writer.transport.abort()
            server.close()

        assert [i.key for i in seen] == ["k"], "the local eviction must survive the timeout"
