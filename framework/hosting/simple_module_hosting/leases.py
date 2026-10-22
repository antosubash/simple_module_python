"""Pick and install the process-wide lease backend (GH #539).

Redis when ``SM_REDIS_URL`` is set, else the ``sm_lease`` table on the app's
database, else in-process. :func:`create_app` installs it from the engine it
builds; a Celery worker never builds the app, so its bootstrap calls
:func:`configure_process_leases` with the URLs it resolved.
"""

from __future__ import annotations

import logging

from simple_module_core.leases import InProcessLeaseBackend, LeaseBackend, configure_leases
from simple_module_db.leases import DbLeaseBackend
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from simple_module_hosting._lease_redis import RedisLeaseBackend

__all__ = ["RedisLeaseBackend", "build_lease_backend", "configure_process_leases"]

logger = logging.getLogger(__name__)


def build_lease_backend(
    redis_url: str | None,
    *,
    engine: AsyncEngine | None = None,
    database_url: str | None = None,
) -> LeaseBackend:
    """Redis → *engine* (or a pool-less engine on *database_url*) → in-process."""
    if redis_url:
        return RedisLeaseBackend(redis_url)
    if engine is None and database_url:
        from simple_module_db.session import init_db

        # No pool: a worker may run each task in its own event loop, and a
        # pooled async connection cannot cross loops.
        engine = init_db(database_url, poolclass=NullPool).engine
    if engine is not None:
        return DbLeaseBackend(engine)
    return InProcessLeaseBackend()


def configure_process_leases(
    redis_url: str | None,
    *,
    engine: AsyncEngine | None = None,
    database_url: str | None = None,
) -> LeaseBackend:
    """Build the backend and make it what ``lease()`` / ``semaphore()`` use."""
    backend = build_lease_backend(redis_url, engine=engine, database_url=database_url)
    configure_leases(backend)
    logger.debug("Leases use %s", type(backend).__name__)
    return backend
