"""Build and configure the Celery application.

Invoked from two places:

- :meth:`BackgroundTasksModule.on_startup` in the web process, so the API
  can enqueue tasks via ``app.state.background_tasks.celery.send_task(...)``.
- ``scripts/run_worker.py`` at worker boot, so the worker process uses an
  identical config (broker URL, signal handlers, autodiscovered tasks).

Task discovery uses :py:meth:`celery.Celery.autodiscover_tasks` with the
top-level package name of every installed module (enumerated via the
``simple_module`` entry-point group). Any module that ships a ``tasks.py``
is picked up automatically — no framework hook, no per-module registration.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points

from celery import Celery
from celery.schedules import schedule

from background_tasks.constants import (
    INTERNAL_TASK_PURGE_OLD,
    INTERNAL_TASK_SWEEP_STUCK,
    MODULE_NAME,
)
from background_tasks.settings import BackgroundTasksSettings

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "simple_module"


def _discover_task_packages() -> list[str]:
    """Return the top-level package name of every installed simple_module.

    Celery's ``autodiscover_tasks`` imports ``<package>.tasks`` for each name
    returned here, so any module that ships a ``tasks.py`` registers its
    tasks without a per-module hook.
    """
    packages: set[str] = set()
    for ep in entry_points(group=_ENTRY_POINT_GROUP):
        # ep.value looks like "background_tasks.module:BackgroundTasksModule".
        # We want just the top-level package name.
        module_path = ep.value.split(":", 1)[0]
        top_level = module_path.split(".", 1)[0]
        packages.add(top_level)
    return sorted(packages)


def build_celery(settings: BackgroundTasksSettings) -> Celery:
    """Construct a Celery app wired to the project's Redis broker."""
    celery = Celery(MODULE_NAME)

    celery.conf.update(
        broker_url=settings.broker_url,
        result_backend=settings.result_backend,
        task_default_queue=settings.task_default_queue,
        # ``task_track_started`` gives us the ``STARTED`` state so
        # ``task_prerun`` can flip our row to ``running``.
        task_track_started=True,
        # ``task_acks_late`` + ``worker_prefetch_multiplier=1`` gives us
        # at-least-once semantics, which matches how the admin UI asks users
        # to think about retries — duplicates beat lost work.
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        broker_connection_retry_on_startup=True,
        beat_schedule={
            "background-tasks-sweep-stuck": {
                "task": INTERNAL_TASK_SWEEP_STUCK,
                "schedule": schedule(settings.stuck_sweep_interval_seconds),
            },
            "background-tasks-purge-old": {
                "task": INTERNAL_TASK_PURGE_OLD,
                "schedule": schedule(settings.purge_interval_seconds),
            },
        },
        beat_scheduler="celery.beat:PersistentScheduler",
    )

    # Autodiscover across every installed simple_module — a module just ships
    # a `tasks.py` and the worker picks it up.
    packages = _discover_task_packages()
    logger.info("Celery autodiscover_tasks across: %s", packages)
    celery.autodiscover_tasks(packages, related_name="tasks", force=True)

    # Side-effect import: connects signal handlers to this Celery instance's
    # ``celery.signals.*`` globals. Safe to import repeatedly.
    from background_tasks import signals  # noqa: F401

    return celery
