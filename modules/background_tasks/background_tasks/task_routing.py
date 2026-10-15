"""Per-module task routing, queue membership and package selection.

A module may ship a light ``<pkg>/task_config.py`` exporting any of:

- ``TASK_ROUTES``: Celery ``task_routes`` entries (glob patterns allowed; a
  value is a queue name or a full route dict).
- ``QUEUES``: the queues the module's tasks run on. Defaults to the install's
  ``task_default_queue``.
- ``BEAT_SCHEDULE``: periodic entries, merged over ``tasks.BEAT_SCHEDULE``.

It is read *without* importing ``tasks.py``, so a worker started with a queue
subset can decide which modules to load without importing the heavy ones.
Keep it free of heavy imports (and of celery).
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any

from background_tasks.settings import BackgroundTasksSettings

logger = logging.getLogger(__name__)

OVERRIDE_SOURCE = "override"


@dataclass(frozen=True)
class ModuleTaskConfig:
    package: str
    routes: dict[str, Any] = field(default_factory=dict)
    queues: frozenset[str] | None = None
    beat_schedule: dict[str, Any] = field(default_factory=dict)


def load_task_config(package: str) -> ModuleTaskConfig | None:
    """Import ``<package>.task_config``; ``None`` when the module ships none."""
    try:
        mod = importlib.import_module(f"{package}.task_config")
    except ModuleNotFoundError as exc:
        # Only "no task_config.py" is absence; a task_config whose own import
        # fails must surface.
        if exc.name in (package, f"{package}.task_config"):
            return None
        raise
    routes = getattr(mod, "TASK_ROUTES", None)
    queues = getattr(mod, "QUEUES", None)
    beat = getattr(mod, "BEAT_SCHEDULE", None)
    return ModuleTaskConfig(
        package=package,
        routes=dict(routes) if isinstance(routes, dict) else {},
        queues=frozenset(queues) if isinstance(queues, (set, frozenset, list, tuple)) else None,
        beat_schedule=dict(beat) if isinstance(beat, dict) else {},
    )


def load_task_configs(packages: list[str]) -> dict[str, ModuleTaskConfig]:
    configs: dict[str, ModuleTaskConfig] = {}
    for pkg in packages:
        cfg = load_task_config(pkg)
        if cfg is not None:
            configs[pkg] = cfg
    return configs


def route_queue(value: Any) -> str:
    """The queue a ``task_routes`` value names ('' when it names none)."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("queue") or "")
    return ""


def merge_routes(
    configs: dict[str, ModuleTaskConfig], override: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Merge module routes (sorted package order, first wins) then the override.

    Returns the ``task_routes`` mapping and a flat ``[{pattern, queue, module}]``
    list describing where each effective entry came from.
    """
    routes: dict[str, Any] = {}
    owner: dict[str, str] = {}
    for pkg in sorted(configs):
        for pattern, value in configs[pkg].routes.items():
            if pattern in routes:
                logger.warning(
                    "Task route %r from %s clashes with %s; keeping %s's entry",
                    pattern,
                    pkg,
                    owner[pattern],
                    owner[pattern],
                )
                continue
            routes[pattern] = value
            owner[pattern] = pkg
    for pattern, value in override.items():
        routes[pattern] = value
        owner[pattern] = OVERRIDE_SOURCE
    info = [{"pattern": p, "queue": route_queue(v), "module": owner[p]} for p, v in routes.items()]
    return routes, info


def select_packages(
    packages: list[str],
    configs: dict[str, ModuleTaskConfig],
    settings: BackgroundTasksSettings,
) -> list[str]:
    """Packages this process imports ``tasks.py`` for.

    Order: ``exclude_modules`` always loses; then ``include_modules`` always
    wins; then, when ``worker_queues`` is set, a package needs a queue overlap;
    otherwise every package is loaded.
    """
    exclude = set(settings.exclude_modules)
    include = set(settings.include_modules)
    wanted = set(settings.worker_queues)
    selected: list[str] = []
    for pkg in packages:
        if pkg in exclude:
            continue
        if pkg in include or not wanted:
            selected.append(pkg)
            continue
        cfg = configs.get(pkg)
        queues = cfg.queues if cfg is not None and cfg.queues is not None else None
        if queues is None:
            queues = frozenset({settings.task_default_queue})
        if queues & wanted:
            selected.append(pkg)
    return selected
