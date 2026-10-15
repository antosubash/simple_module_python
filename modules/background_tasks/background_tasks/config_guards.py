"""Guards for operator-supplied Celery configuration.

Celery conf can name serializers (``pickle``), dotted paths it imports on boot
(``imports``, ``worker_pool``, ``beat_scheduler`` ...) and signing material, so
a raw conf dict is a code-execution surface for whoever can write it. Two
inputs reach ``build_celery``:

- ``SM_BG_TASKS_CELERY_OVERRIDES`` (JSON object): environment only, so it is
  controlled by whoever deploys the process and never by an admin-UI editor.
  It is read here rather than being a ``BackgroundTasksSettings`` field, because
  every field of that class is stored in, and hydrated from, the database.
  Dangerous keys are refused even from here.
- ``SM_BG_TASKS_WORKER_QUEUES`` / ``_INCLUDE_MODULES`` / ``_EXCLUDE_MODULES``
  (comma-separated): which queues and modules *this one worker process*
  serves. Environment only for the same reason: one stored value would
  re-scope every worker. All three go through the helpers below.
- ``task_routes_override`` (DB-backed, admin-editable): only names queues, and
  is reduced to plain queue names and route dicts with a closed key set. A route
  dict is merged into ``apply_async`` options, so ``serializer``, ``link`` and
  friends must not be expressible.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from background_tasks.constants import ENV_PREFIX

logger = logging.getLogger(__name__)

ENV_CELERY_OVERRIDES = f"{ENV_PREFIX}CELERY_OVERRIDES"
ENV_WORKER_QUEUES = f"{ENV_PREFIX}WORKER_QUEUES"
ENV_INCLUDE_MODULES = f"{ENV_PREFIX}INCLUDE_MODULES"
ENV_EXCLUDE_MODULES = f"{ENV_PREFIX}EXCLUDE_MODULES"

# Conf keys that choose a (de)serializer or load code by dotted path / file.
_DENIED_KEYS = frozenset(
    {
        "accept_content",
        "task_serializer",
        "result_serializer",
        "result_accept_content",
        "event_serializer",
        "imports",
        "include",
        "worker_pool",
        "worker_autoscaler",
        "worker_consumer",
        "worker_timer",
        "beat_scheduler",
        "beat_schedule",
        "beat_schedule_filename",
        "task_routes",
        "task_annotations",
        "task_queues",
        "task_cls",
        "broker_transport",
        "result_backend_transport_options",
        "worker_state_db",
    }
)
_DENIED_SUBSTRINGS = ("hijack", "serializer", "accept_content", "pickle")
_DENIED_PREFIXES = ("security_", "worker_pool_", "pool_")
_DENIED_SUFFIXES = ("_cls", "_class")


def is_denied_key(key: str) -> bool:
    """True for a conf key that must not be settable from configuration."""
    # Celery also resolves the old ``CELERY_*`` spellings.
    k = key.strip().lower().removeprefix("celery_")
    return (
        k in _DENIED_KEYS
        or k.startswith(_DENIED_PREFIXES)
        or k.endswith(_DENIED_SUFFIXES)
        or any(s in k for s in _DENIED_SUBSTRINGS)
    )


def filter_celery_overrides(raw: object, *, source: str = "celery_overrides") -> dict[str, Any]:
    """Drop (and log) denied keys; non-dict input yields ``{}``."""
    if not isinstance(raw, dict):
        if raw not in (None, {}):
            logger.error("%s must be a JSON object; ignoring it", source)
        return {}
    safe: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or is_denied_key(key):
            logger.error(
                "%s: refusing Celery conf key %r (serializer, import and code-loading "
                "keys cannot be set from configuration); ignoring it",
                source,
                key,
            )
            continue
        safe[key] = value
    return safe


def _env_text(name: str) -> str:
    return os.environ.get(name, "").strip()


def env_csv(name: str) -> list[str]:
    """A comma-separated environment variable as a list (``[]`` when unset)."""
    return [part.strip() for part in _env_text(name).split(",") if part.strip()]


def env_json_object(name: str) -> dict[str, Any]:
    """A JSON-object environment variable (``{}`` when unset or unusable, with a log)."""
    raw = _env_text(name)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        logger.error("%s is not valid JSON (%s); ignoring it", name, exc)
        return {}
    if not isinstance(parsed, dict):
        logger.error("%s must be a JSON object; ignoring it", name)
        return {}
    return parsed


def celery_overrides_from_env() -> dict[str, Any]:
    """The vetted ``SM_BG_TASKS_CELERY_OVERRIDES`` mapping (``{}`` when unset)."""
    return filter_celery_overrides(
        env_json_object(ENV_CELERY_OVERRIDES), source=ENV_CELERY_OVERRIDES
    )


@dataclass(frozen=True)
class WorkerScope:
    """What this process serves; see :func:`worker_scope_from_env`."""

    queues: frozenset[str] = frozenset()
    include_modules: frozenset[str] = frozenset()
    exclude_modules: frozenset[str] = frozenset()


def worker_scope_from_env() -> WorkerScope:
    """Per-process queue/module subset (GH #450), from the environment only."""
    return WorkerScope(
        queues=frozenset(env_csv(ENV_WORKER_QUEUES)),
        include_modules=frozenset(env_csv(ENV_INCLUDE_MODULES)),
        exclude_modules=frozenset(env_csv(ENV_EXCLUDE_MODULES)),
    )


_QUEUE_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,255}$")
_ROUTE_KEYS = frozenset({"queue", "exchange", "routing_key", "priority"})


def _safe_route(value: object) -> object | None:
    if isinstance(value, str):
        return value if _QUEUE_RE.match(value) else None
    if not isinstance(value, dict) or set(value) - _ROUTE_KEYS:
        return None
    queue = value.get("queue")
    if not isinstance(queue, str) or not _QUEUE_RE.match(queue):
        return None
    for key in ("exchange", "routing_key"):
        if key in value and not (isinstance(value[key], str) and _QUEUE_RE.match(value[key])):
            return None
    priority = value.get("priority")
    if "priority" in value and (isinstance(priority, bool) or not isinstance(priority, int)):
        return None
    return dict(value)


def sanitize_task_routes(raw: object) -> dict[str, Any]:
    """Keep only ``{pattern: queue-name | {queue, exchange, routing_key, priority}}``."""
    if not isinstance(raw, dict):
        return {}
    clean: dict[str, Any] = {}
    for pattern, value in raw.items():
        route = _safe_route(value)
        if not isinstance(pattern, str) or not pattern.strip() or route is None:
            logger.error(
                "task_routes_override: refusing entry %r (needs a task pattern and a queue "
                "name or a route dict using only %s); ignoring it",
                pattern,
                sorted(_ROUTE_KEYS),
            )
            continue
        clean[pattern] = route
    return clean


def parse_task_routes(raw: object) -> dict[str, Any]:
    """Strict form of :func:`sanitize_task_routes` for user input.

    Accepts a mapping or a JSON string of one (what the admin settings text box
    submits) and raises ``ValueError`` naming the first bad entry instead of
    silently dropping it, so the editor can show why a save was refused.
    """
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            raise ValueError(f"task_routes_override is not valid JSON: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(
            'task_routes_override must be a JSON object such as {"reports.*": "heavy"}'
        )
    for pattern, value in raw.items():
        if not isinstance(pattern, str) or not pattern.strip() or _safe_route(value) is None:
            raise ValueError(
                f"task_routes_override entry {pattern!r} needs a task pattern and a queue "
                f"name or a route dict using only {sorted(_ROUTE_KEYS)}"
            )
    return dict(raw)
