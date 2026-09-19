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


class TestMuteBrokerListener:
    """The listener must notice a broker that accepts and then says nothing.

    This was a real defect, found by QA after the feature shipped and after the
    first round of these tests passed. ``socket_connect_timeout`` bounds the
    connect and nothing else, so against a mute peer ``pubsub.subscribe()`` waited
    on a read with no deadline: the listener hung before it had ever raised, so
    ``_log_failure`` never ran, the reconnect loop never got a turn, and
    ``_start_invalidation_transport`` had already logged that the transport was up.
    Cross-process invalidation was then off on that worker for the life of the
    process, silently, with the boot log claiming otherwise — strictly worse than
    installing no transport at all.

    The observable property is therefore "it complains": a warning naming the
    consequence, which is what puts the worker back into the reconnect loop.
    """

    async def test_a_mute_broker_makes_the_listener_complain(self, monkeypatch, caplog):
        import logging

        import background_tasks.invalidation as bg_invalidation

        writers: list[asyncio.StreamWriter] = []

        async def hold(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writers.append(writer)
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.Event().wait()

        server = await asyncio.start_server(hold, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(bg_invalidation, "SUBSCRIBE_TIMEOUT_SECONDS", 0.3)
        monkeypatch.setattr(bg_invalidation, "INITIAL_BACKOFF_SECONDS", 0.05)
        caplog.set_level(logging.WARNING)

        transport = RedisInvalidationTransport(
            InvalidationBus(), f"redis://127.0.0.1:{port}/0", _CHANNEL
        )
        await transport.start()
        try:
            deadline = asyncio.get_running_loop().time() + 15
            while asyncio.get_running_loop().time() < deadline:
                if any("keep cached values until they expire" in r.message for r in caplog.records):
                    break
                await asyncio.sleep(0.05)
            else:
                raise AssertionError(
                    "the listener never complained about a mute broker — it is wedged "
                    "in an unbounded read and will never reconnect"
                )
        finally:
            await transport.stop()
            for writer in writers:
                writer.transport.abort()
            server.close()

    async def test_stop_still_returns_promptly_while_wedged(self, monkeypatch):
        """Shutdown must not inherit the listener's problem.

        ``on_shutdown`` awaits ``stop()``, so a listener stuck on a read would
        hang the whole application shutdown.
        """
        import background_tasks.invalidation as bg_invalidation

        writers: list[asyncio.StreamWriter] = []

        async def hold(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writers.append(writer)
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.Event().wait()

        server = await asyncio.start_server(hold, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(bg_invalidation, "SUBSCRIBE_TIMEOUT_SECONDS", 30.0)

        transport = RedisInvalidationTransport(
            InvalidationBus(), f"redis://127.0.0.1:{port}/0", _CHANNEL
        )
        await transport.start()
        await asyncio.sleep(0.2)
        try:
            await asyncio.wait_for(transport.stop(), timeout=20)
        finally:
            for writer in writers:
                writer.transport.abort()
            server.close()


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

        The client now also carries ``socket_timeout`` (see F7 — the listener
        needed it), which bounds this too, but at ten seconds rather than one. The
        publish keeps its own tighter bound because it is the only one of the two
        that sits in a user's way. Setting ``socket_timeout`` that low instead is
        not an option: the same client serves the subscription, and a quiet
        channel must not be torn down for being quiet.
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
