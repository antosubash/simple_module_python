"""Hydrated DB-backed module settings for task code (GH #378).

A Celery worker never runs the hosting lifespan that hydrates
``app.state.<package>.settings``, and ``DbBackedSettings`` ignores the
environment, so a bare ``FileStorageSettings()`` in a task returns pydantic
defaults without complaint. Use :func:`settings_for` instead::

    cfg = settings_for(FileStorageSettings, "file_storage")

It reads the SYSTEM-scope overrides through the worker's sync session and
caches the result per process for ``DEFAULT_TTL_SECONDS`` so a hot task does not
query on every call. Admin edits therefore reach a worker within the TTL.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import cast

from pydantic_settings import BaseSettings
from simple_module_db.stored_settings import hydrate_settings_sync

from background_tasks.constants import MODULE_NAME
from background_tasks.settings import BackgroundTasksSettings
from background_tasks.sync_db import sync_session

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 30.0

_lock = threading.Lock()
_cache: dict[tuple[type, str], tuple[float, BaseSettings]] = {}


def settings_for[T: BaseSettings](
    cls: type[T], package: str, *, ttl: float = DEFAULT_TTL_SECONDS
) -> T:
    """Return ``cls`` hydrated from DB overrides, cached per process for ``ttl`` seconds.

    ``ttl=0`` always re-reads.
    """
    key = (cls, package)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit is not None and ttl > 0 and now - hit[0] < ttl:
            # A copy: BaseSettings is mutable, so one task editing its settings
            # must not change what the next task in this process sees.
            return cast(T, hit[1]).model_copy(deep=True)
    with sync_session() as session:
        value = hydrate_settings_sync(cls, session, package, lenient=True)
    with _lock:
        _cache[key] = (now, value)
    return value.model_copy(deep=True)


def clear_settings_cache() -> None:
    """Drop every cached settings object (tests, or after a known write)."""
    with _lock:
        _cache.clear()


def load_runner_settings() -> BackgroundTasksSettings:
    """``BackgroundTasksSettings`` for the worker/beat process, DB overrides included.

    ``scripts/run_worker.py`` used to build these from the environment alone, so
    an admin's DB-backed edit (a queue, a time limit)
    reached the web process but never the worker, and the two disagreed on
    config. Hydration is the same call the web lifespan makes (``cls(**db_overrides)``),
    so precedence matches the web process: env → DB → default (GH #486). If the DB is
    unreachable or not yet migrated the worker still boots on env/defaults,
    loudly, rather than refusing to start.
    """
    try:
        return settings_for(BackgroundTasksSettings, MODULE_NAME, ttl=0)
    except Exception:
        logger.warning(
            "Could not read background_tasks settings from the database; "
            "starting from environment/defaults only",
            exc_info=True,
        )
        return BackgroundTasksSettings()
