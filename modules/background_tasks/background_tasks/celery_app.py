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

import importlib
import logging
from importlib.metadata import entry_points

from celery import Celery
from celery.schedules import schedule
from simple_module_core.discovery import ENTRY_POINT_GROUP

from background_tasks.constants import (
    INTERNAL_TASK_PURGE_OLD,
    INTERNAL_TASK_SWEEP_STUCK,
    MODULE_NAME,
)
from background_tasks.settings import BackgroundTasksSettings
from background_tasks.task_routing import load_task_configs, merge_routes, select_packages

logger = logging.getLogger(__name__)


def _discover_task_packages() -> list[str]:
    """Return the top-level package name of every installed simple_module.

    Celery's ``autodiscover_tasks`` imports ``<package>.tasks`` for each name
    returned here, so any module that ships a ``tasks.py`` registers its
    tasks without a per-module hook.
    """
    packages: set[str] = set()
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        module_path = ep.value.split(":", 1)[0]
        top_level = module_path.split(".", 1)[0]
        packages.add(top_level)
    return sorted(packages)


def _collect_module_beat_schedules(packages: list[str]) -> dict:
    """Merge every installed module's optional ``tasks.BEAT_SCHEDULE`` mapping.

    A module registers periodic work the same way it registers tasks — by
    shipping a ``tasks.py`` — and additionally exporting a module-level
    ``BEAT_SCHEDULE`` dict of ``{entry_name: celery beat entry}``. Because
    ``build_celery`` runs identically in the web and worker processes, this is
    worker-safe and deterministic, unlike runtime registration via
    ``add_periodic_task`` / the ``on_after_finalize`` signal (and unlike the
    commonly-cited ``on_after_configure``, which never fires here — see GH #199).

    Importing ``<pkg>.tasks`` is idempotent (autodiscover imports the same
    modules), so doing it eagerly here has no extra side effects.
    """
    merged: dict = {}
    for pkg in packages:
        try:
            tasks_mod = importlib.import_module(f"{pkg}.tasks")
        except ModuleNotFoundError as exc:
            # The module simply ships no tasks.py — skip. But a tasks.py that
            # *exists* and fails to import (its own dependency is missing) must
            # surface loudly, not be mistaken for "no tasks.py" and silently
            # drop the module's periodic work.
            if exc.name in (pkg, f"{pkg}.tasks"):
                continue
            raise
        schedule_dict = getattr(tasks_mod, "BEAT_SCHEDULE", None)
        if not isinstance(schedule_dict, dict):
            continue
        for name, entry in schedule_dict.items():
            if name in merged:
                logger.warning(
                    "Beat entry %r from %s.tasks overrides an earlier module's entry", name, pkg
                )
            merged[name] = entry
    return merged


# setting name -> Celery conf key (they differ only for the memory cap, which
# Celery names without the unit although it is KiB).
_TUNING_KEYS = {
    "worker_max_tasks_per_child": "worker_max_tasks_per_child",
    "worker_max_memory_per_child_kb": "worker_max_memory_per_child",
    "task_reject_on_worker_lost": "task_reject_on_worker_lost",
    "task_soft_time_limit": "task_soft_time_limit",
    "task_time_limit": "task_time_limit",
    "worker_concurrency": "worker_concurrency",
}


def _tuning_conf(settings: BackgroundTasksSettings) -> dict:
    """Celery conf for the optional tuning fields; ``None`` keeps Celery's default."""
    conf = {
        key: getattr(settings, name)
        for name, key in _TUNING_KEYS.items()
        if getattr(settings, name) is not None
    }
    if settings.visibility_timeout_seconds is not None:
        conf["broker_transport_options"] = {
            "visibility_timeout": settings.visibility_timeout_seconds
        }
    return conf


def describe_routes(settings: BackgroundTasksSettings) -> list[dict[str, str]]:
    """Effective ``[{pattern, queue, module}]`` routes, for the Workers admin page."""
    configs = load_task_configs(_discover_task_packages())
    return merge_routes(configs, settings.task_routes_override)[1]


def build_celery(settings: BackgroundTasksSettings) -> Celery:
    """Construct a Celery app wired to the project's Redis broker."""
    celery = Celery(MODULE_NAME)

    all_packages = _discover_task_packages()
    # Routes and beat entries come from the light ``task_config`` of *every*
    # module; only the heavy ``tasks.py`` imports are narrowed to this
    # process's subset (GH #450).
    configs = load_task_configs(all_packages)
    packages = select_packages(all_packages, configs, settings)
    task_routes, _ = merge_routes(configs, settings.task_routes_override)

    # The two internal entries always ship; modules contribute more via their
    # own ``tasks.BEAT_SCHEDULE``. ``setdefault`` keeps the built-ins authoritative
    # if a module reuses one of their entry names. See GH #199.
    beat_schedule = {
        "background-tasks-sweep-stuck": {
            "task": INTERNAL_TASK_SWEEP_STUCK,
            "schedule": schedule(settings.stuck_sweep_interval_seconds),
        },
        "background-tasks-purge-old": {
            "task": INTERNAL_TASK_PURGE_OLD,
            "schedule": schedule(settings.purge_interval_seconds),
        },
    }
    for name, entry in _collect_module_beat_schedules(packages).items():
        if name in beat_schedule:
            logger.warning(
                "Module beat entry %r clashes with a built-in entry; the built-in wins", name
            )
            continue
        beat_schedule[name] = entry
    # ``task_config.BEAT_SCHEDULE`` wins over the same entry in ``tasks.py``.
    for pkg in sorted(configs):
        for name, entry in configs[pkg].beat_schedule.items():
            if name in beat_schedule and name in (
                "background-tasks-sweep-stuck",
                "background-tasks-purge-old",
            ):
                logger.warning(
                    "task_config beat entry %r clashes with a built-in; built-in wins", name
                )
                continue
            beat_schedule[name] = entry

    celery.conf.update(
        broker_url=settings.broker_url,
        result_backend=settings.result_backend,
        task_default_queue=settings.task_default_queue,
        # Run tasks synchronously inside the calling process. Tests
        # toggle this on (via ``SM_BG_TASKS_TASK_ALWAYS_EAGER=true``) so
        # ``task.delay()`` doesn't reach for a real broker.
        task_always_eager=settings.task_always_eager,
        task_eager_propagates=settings.task_eager_propagates,
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
        beat_schedule=beat_schedule,
        beat_scheduler="celery.beat:PersistentScheduler",
        task_routes=task_routes,
    )
    celery.conf.update(_tuning_conf(settings))
    if settings.celery_overrides:
        logger.info("Applying celery_overrides: %s", sorted(settings.celery_overrides))
        celery.conf.update(settings.celery_overrides)

    # Autodiscover across every installed simple_module — a module just ships
    # a `tasks.py` and the worker picks it up.
    logger.info("Celery autodiscover_tasks across: %s", packages)
    celery.autodiscover_tasks(packages, related_name="tasks", force=True)

    # Side-effect import: connects signal handlers to this Celery instance's
    # ``celery.signals.*`` globals. Safe to import repeatedly.
    from background_tasks import signals  # noqa: F401
    from background_tasks.log_context import install_log_filter

    install_log_filter()

    return celery
