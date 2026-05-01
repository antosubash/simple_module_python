"""Read-only adapter around ``celery.control.inspect()``.

Produces a :class:`WorkerSnapshot` for the admin Workers page. All broker
errors are caught and surfaced through ``snapshot.broker_reachable`` /
``snapshot.error`` so the page can render a clear operator-facing state
instead of the endpoint returning a 5xx.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from kombu.exceptions import OperationalError
from redis.exceptions import RedisError

from background_tasks.contracts.schemas import WorkerInfo, WorkerSnapshot

if TYPE_CHECKING:
    from celery import Celery

logger = logging.getLogger(__name__)


class WorkerInspector:
    """Synchronous adapter; call from async code via ``asyncio.to_thread``."""

    def __init__(self, celery: Celery, *, timeout: float = 1.0) -> None:
        self.celery = celery
        self.timeout = timeout

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
                error=str(exc),
            )

        inspect = self.celery.control.inspect(timeout=self.timeout)
        try:
            ping = inspect.ping() or {}
            stats = inspect.stats() or {}
            queues = inspect.active_queues() or {}
            active = inspect.active() or {}
        except (OperationalError, RedisError, ConnectionError, OSError) as exc:
            logger.info("inspect() failed mid-call: %s", exc)
            return WorkerSnapshot(
                broker_reachable=False,
                polled_at=polled_at,
                workers=[],
                error=str(exc),
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

    return WorkerInfo(
        hostname=hostname,
        online=pinged,
        queues=[q.get("name", "") for q in queues if q.get("name")],
        active_task_count=len(active),
        pool_size=pool_size,
        total_processed=total_processed,
        software=software,
    )
