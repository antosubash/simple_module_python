"""Redis pub/sub transport for the framework's :class:`InvalidationBus`.

This module owns the app's Redis connection already — one URL, one set of
settings, one health check. Cross-process cache invalidation needs exactly that
connection and nothing else, so it is installed from here rather than opened a
second time inside whichever module happens to keep a cache (GH #318). A module
→ framework import is fine; the reverse is what ``SM009`` forbids, which is why
the bus itself knows nothing about Redis.

Every framework channel shares one Redis channel. The volume is a handful of
messages per revocation — ``users`` is the only publisher today — and
``Invalidation.channel`` routes
inside the receiving process, so one subscription is less machinery for the same
result — and it means a module that adds a channel after boot needs no
resubscribe.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simple_module_core.invalidation import InvalidationBus

logger = logging.getLogger(__name__)

__all__ = ["RedisInvalidationTransport"]

INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0

SUBSCRIBE_TIMEOUT_SECONDS = 5.0
"""Ceiling on the one-shot SUBSCRIBE at the top of each listener attempt.

A separate bound from :data:`PUBLISH_TIMEOUT_SECONDS` because it is not in a
request's way — only a wedged listener's. Needed because ``socket_connect_timeout``
bounds the *connect* and nothing else: against a broker that completes the TCP
handshake and then never answers, ``subscribe`` waits on a read that has no
deadline, so the listener hangs before it has ever raised, ``_log_failure`` never
runs, and the reconnect loop below never gets a turn. Cross-process invalidation
is then silently and permanently off on this worker, while the boot log says it is
on — the exact "does nothing and nobody learns" failure this whole file is
supposed to avoid. Found by QA, not by the original tests.
"""

READ_TIMEOUT_SECONDS = 10.0
"""``socket_timeout`` for the client: a bound on any read that has started.

Cannot simply be small: the same option applies to the subscription, and a quiet
channel must not be torn down for being quiet. That is why the listener polls
:meth:`redis.asyncio.client.PubSub.get_message` with its own short timeout instead
of blocking in ``listen()`` — polling returns ``None`` on an idle channel without
ever starting a read, so this deadline only bites when bytes stop arriving
mid-message.
"""

HEALTH_CHECK_INTERVAL_SECONDS = 15.0
"""How often redis-py PINGs an otherwise idle subscription.

The half-open socket — ESTABLISHED at both ends, carrying nothing, as a NAT or
load balancer idle-drop leaves it — is invisible to every timeout above, because
no read is ever attempted. redis-py's health check is what turns it into an error:
the PING's reply read is bounded by ``socket_timeout``, so a mute peer raises into
the reconnect loop within roughly this interval.
"""

LISTEN_POLL_SECONDS = 1.0
"""How long each ``get_message`` waits before returning ``None`` and looping.

Also the granularity at which the health check and cancellation get a turn.
"""

PUBLISH_TIMEOUT_SECONDS = 1.0
"""Ceiling on how long a publish may hold up the request that triggered it.

``publish`` is awaited inside the response cycle — a password change's
``db.on_commit`` callback runs before the response is sent — and redis-py
defaults to *no* socket timeout, so a Redis that accepts connections but stops
answering would hang that request indefinitely rather than degrade the fan-out.
One second is far more than a local round trip needs and far less than a user
waits. Exceeding it raises, which the bus logs and swallows: the local eviction
has already happened, so the cost of the timeout is the same staleness window
that existed before this transport.
"""


class RedisInvalidationTransport:
    """Publishes to, and listens on, one Redis pub/sub channel.

    Satisfies ``simple_module_core.invalidation.InvalidationTransport``
    structurally — no import of the Protocol at runtime, so this file costs
    nothing when the bus is unused.
    """

    def __init__(self, bus: InvalidationBus, url: str, channel: str) -> None:
        self._bus = bus
        self._url = url
        self._channel = channel
        self._client = None
        self._listener: asyncio.Task | None = None
        self._warned = False

    async def start(self) -> None:
        """Open the client and start the listener task.

        Does **not** wait for a successful connection, and does not raise if
        Redis is down. Invalidation is an accelerator over a TTL that already
        bounds staleness, so an unreachable broker must degrade the app to
        per-process caching — its behaviour before this existed — rather than
        fail the boot of a web worker that can otherwise serve every request.
        ``/health`` already reports Redis; this logs a warning naming the
        consequence so the two agree.
        """
        import redis.asyncio as aioredis

        # Four deadlines, each covering a failure the others do not. Connect
        # covers a host that swallows SYN packets; socket_timeout covers a read
        # that starts and stalls; keepalive and the health check cover a socket
        # that is open at both ends and carrying nothing. Without the last two a
        # half-open connection leaves this worker permanently and silently
        # without cross-process invalidation.
        self._client = aioredis.from_url(
            self._url,
            socket_connect_timeout=PUBLISH_TIMEOUT_SECONDS,
            socket_timeout=READ_TIMEOUT_SECONDS,
            socket_keepalive=True,
            health_check_interval=HEALTH_CHECK_INTERVAL_SECONDS,
        )
        self._listener = asyncio.create_task(self._listen(), name="sm-invalidation-listener")

    async def publish(self, message: str) -> None:
        """Broadcast one encoded invalidation. Raises — the bus logs it.

        Bounded by :data:`PUBLISH_TIMEOUT_SECONDS`, because this runs inside the
        response cycle of the request that made the write.
        """
        if self._client is None:
            raise RuntimeError("RedisInvalidationTransport.start() was not called")
        async with asyncio.timeout(PUBLISH_TIMEOUT_SECONDS):
            await self._client.publish(self._channel, message)

    async def stop(self) -> None:
        """Cancel the listener and close the client."""
        if self._listener is not None:
            self._listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener
            self._listener = None
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.aclose()
            self._client = None

    async def _listen(self) -> None:
        """Subscribe and hand every message to the bus, reconnecting forever.

        Reconnects rather than giving up after the first failure: a Redis that
        is briefly unreachable during a deploy would otherwise leave this worker
        with cross-process invalidation permanently off, which is the original
        bug wearing a warning message. Backoff is capped so a long outage does
        not turn into a reconnect storm when it ends.

        Only the *first* failure of a run logs at warning. A worker that
        outlives an hour of downtime should not have written an hour of
        identical lines, but the state still has to be visible once.
        """
        backoff = INITIAL_BACKOFF_SECONDS
        while True:
            pubsub = None
            try:
                pubsub = self._client.pubsub()
                async with asyncio.timeout(SUBSCRIBE_TIMEOUT_SECONDS):
                    await pubsub.subscribe(self._channel)
                if self._warned:
                    logger.info("Invalidation listener reconnected to %r", self._channel)
                self._warned = False
                backoff = INITIAL_BACKOFF_SECONDS
                while True:
                    # Polling rather than ``listen()``: an idle channel returns
                    # None instead of blocking in an unbounded read, which is what
                    # lets redis-py run its health check and lets cancellation
                    # land promptly at shutdown.
                    raw = await pubsub.get_message(timeout=LISTEN_POLL_SECONDS)
                    if raw is None or raw.get("type") != "message":
                        continue
                    await self._bus.deliver(raw["data"])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._log_failure(exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            finally:
                if pubsub is not None:
                    with contextlib.suppress(Exception):
                        await pubsub.aclose()

    def _log_failure(self, exc: Exception) -> None:
        """Warn once per outage, then stay quiet about the same outage."""
        if self._warned:
            logger.debug("Invalidation listener still down: %s", exc)
            return
        self._warned = True
        logger.warning(
            "Invalidation listener lost Redis (%s); other workers keep cached "
            "values until they expire. Retrying.",
            exc,
        )
