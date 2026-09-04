"""Read-only adapter around ``celery.control.inspect()``.

Produces a :class:`WorkerSnapshot` for the admin Workers page. All broker
errors are caught and surfaced through ``snapshot.broker_reachable`` /
``snapshot.error`` so the page can render a clear operator-facing state
instead of the endpoint returning a 5xx.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

from kombu.exceptions import OperationalError
from redis.exceptions import RedisError

from background_tasks.contracts.schemas import WorkerInfo, WorkerSnapshot

if TYPE_CHECKING:
    from celery import Celery

logger = logging.getLogger(__name__)


# The four independent inspect broadcasts, issued concurrently.
_PROBES = ("ping", "stats", "active_queues", "active")

# What a stripped password is replaced with, in the url and on the page.
REDACTED = "***"

# A url sitting inside a sentence. Stops at whitespace and at the quoting a
# message is likely to wrap it in; a trailing ':' or '.' is shed so
# "connect to redis://h:1/0: timed out" does not swallow the rest.
_URL_IN_TEXT = re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s'\"<>]*[^\s'\"<>.,:;]")


class WorkerInspector:
    """Synchronous adapter; call from async code via ``asyncio.to_thread``."""

    def __init__(self, celery: Celery, *, timeout: float = 1.0) -> None:
        self.celery = celery
        self.timeout = timeout

    def _probe(self, name: str) -> dict:
        """Run one inspect broadcast on its own handle. ``None`` means nobody replied."""
        inspect = self.celery.control.inspect(timeout=self.timeout)
        return getattr(inspect, name)() or {}

    def snapshot(self) -> WorkerSnapshot:
        polled_at = datetime.now(UTC)

        # Probe the broker first so we can distinguish "broker down" from
        # "broker up but no workers replied". Without this, both look like
        # ``inspect.*() == None``.
        try:
            with self.celery.connection() as conn:
                conn.ensure_connection(max_retries=1, timeout=self.timeout)
        except (OperationalError, RedisError, ConnectionError, OSError) as exc:
            logger.info("Broker unreachable: %s", exc)
            return WorkerSnapshot(
                broker_reachable=False,
                polled_at=polled_at,
                workers=[],
                error=redact_urls(str(exc)),
            )

        # Each inspect call broadcasts and then waits the *full* timeout for
        # replies — it cannot know whether a slow worker is still coming. Run
        # sequentially that is 4 x timeout, so with the broker up and no
        # workers this page took ~4s: precisely the state an admin opens it to
        # diagnose. The four probes are independent, so issue them together
        # and the page costs one timeout instead of four.
        #
        # Each gets its own inspect handle rather than sharing one across
        # threads. Results are still merged by hostname afterwards, so a
        # worker that answers some probes but not others (a degraded worker)
        # is still reported.
        try:
            with ThreadPoolExecutor(max_workers=len(_PROBES)) as pool:
                futures = {name: pool.submit(self._probe, name) for name in _PROBES}
                ping = futures["ping"].result()
                stats = futures["stats"].result()
                queues = futures["active_queues"].result()
                active = futures["active"].result()
        except (OperationalError, RedisError, ConnectionError, OSError) as exc:
            logger.info("inspect() failed mid-call: %s", exc)
            return WorkerSnapshot(
                broker_reachable=False,
                polled_at=polled_at,
                workers=[],
                error=redact_urls(str(exc)),
            )

        hostnames = sorted(set(ping) | set(stats) | set(queues) | set(active))
        workers = [
            _build_worker_info(
                hostname=h,
                pinged=h in ping,
                stats=stats.get(h) or {},
                queues=queues.get(h) or [],
                active=active.get(h) or [],
            )
            for h in hostnames
        ]
        return WorkerSnapshot(
            broker_reachable=True,
            polled_at=polled_at,
            workers=workers,
            error=None,
        )


def _build_worker_info(
    *,
    hostname: str,
    pinged: bool,
    stats: dict[str, Any],
    queues: list[dict[str, Any]],
    active: list[dict[str, Any]],
) -> WorkerInfo:
    pool = stats.get("pool") or {}
    pool_size = pool.get("max-concurrency")
    if pool_size is None and isinstance(pool.get("processes"), list):
        pool_size = len(pool["processes"])

    total = stats.get("total")
    total_processed: int | None = None
    if isinstance(total, dict):
        total_processed = sum(int(v) for v in total.values() if isinstance(v, int | float))
    elif isinstance(total, int):
        total_processed = total

    sw_ident = stats.get("sw_ident")
    sw_ver = stats.get("sw_ver")
    software = f"{sw_ident}:{sw_ver}" if sw_ident and sw_ver else (sw_ident or sw_ver)

    # Celery reports uptime as a number of seconds. Anything else (a worker
    # running a patched build, a proxy that rewrote the payload) is dropped
    # rather than passed through — a card that renders "uptime ages" is worse
    # than one that admits it doesn't know. ``bool`` is excluded explicitly:
    # it is an ``int`` in Python, and "uptime: True" is not a duration.
    raw_uptime = stats.get("uptime")
    uptime_seconds = (
        float(raw_uptime)
        if isinstance(raw_uptime, int | float) and not isinstance(raw_uptime, bool)
        else None
    )

    return WorkerInfo(
        hostname=hostname,
        online=pinged,
        queues=[q.get("name", "") for q in queues if q.get("name")],
        active_task_count=len(active),
        pool_size=pool_size,
        total_processed=total_processed,
        software=software,
        uptime_seconds=uptime_seconds,
    )


def redact_broker_url(url: str) -> str:
    """Strip the password out of a broker url before it is shown to anyone.

    The Workers page names the url so an operator can check the setting it is
    blaming, and broker urls routinely carry credentials — a redis password
    put on screen (and into every screenshot of a failing deploy) is a leak
    the page has no reason to cause. The username survives, because that is
    part of identifying *which* broker without being a secret.

    Parsing is deliberate rather than regex-based: a password can legally
    contain ``@`` and ``:``, and only a parser gets the last ``@`` right.
    """
    if not url:
        return url
    try:
        parsed = urlsplit(url)
        if not parsed.password:
            return url
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
    except ValueError:
        # ``urlsplit`` defers validation to attribute access, so a malformed
        # port lands here. Unparseable input may still carry a credential —
        # say nothing rather than echo something that might.
        return REDACTED
    netloc = f"{parsed.username or ''}:{REDACTED}@{host}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def redact_urls(text: str | None) -> str | None:
    """Strip credentials out of every url embedded in a free-text message.

    ``snapshot.error`` is ``str(exc)`` from kombu or redis, and those messages
    routinely quote the url they were dialling — password included. Running
    :func:`redact_broker_url` over the whole string does nothing, because a
    sentence is not a url; the url has to be found inside it first.

    Deliberately greedy about what counts as a url and conservative about what
    it does with one: a match with no password comes back unchanged, so the
    message keeps naming the broker an operator is trying to identify.
    """
    if not text:
        return text
    return _URL_IN_TEXT.sub(lambda m: redact_broker_url(m.group(0)), text)
