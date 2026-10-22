"""Celery, worker-tuning, invalidation and retention fields of the module settings.

Split out of ``settings`` by responsibility; ``BackgroundTasksSettings`` inherits
them and adds the durable outbox. Field order is unchanged.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import SettingsConfigDict
from simple_module_core.settings_hydrate import RELATED_FIELDS_CTX

from background_tasks.config_guards import parse_task_routes
from background_tasks.constants import (
    DEFAULT_BROKER_URL,
    DEFAULT_INVALIDATION_CHANNEL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_PURGE_INTERVAL_SECONDS,
    DEFAULT_QUEUE,
    DEFAULT_RESULT_BACKEND,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_STUCK_AFTER_SECONDS,
    DEFAULT_STUCK_SWEEP_INTERVAL_SECONDS,
    ENV_PREFIX,
    ENV_REDIS_URL,
)
from background_tasks.db_settings import WorkerDatabaseSettings
from background_tasks.settings_logs import LogSinkFields

_CELERY_RESTART = {"requires_restart": True, "group": "Celery"}

logger = logging.getLogger(__name__)


def _redis_from_env(default: str) -> str:
    """``SM_REDIS_URL`` → the module default.

    ``env_prefix`` means pydantic's env source has already answered
    ``SM_BG_TASKS_BROKER_URL`` / ``SM_BG_TASKS_RESULT_BACKEND`` by the time a
    default is needed, so this factory is only the ``SM_REDIS_URL`` half — the
    legacy names keep working, and keep winning, through that source instead."""
    return os.environ.get(ENV_REDIS_URL) or default


class CelerySettingsFields(LogSinkFields, WorkerDatabaseSettings):
    """Broker, worker tuning, invalidation and retention fields (see ``settings``)."""

    # Without ``env_prefix`` each field resolved from its bare name, so a
    # container setting ``broker_url`` or ``retention_days`` for another purpose
    # reconfigured Celery and ``SM_BG_TASKS_*`` did nothing (GH #283).
    model_config = SettingsConfigDict(extra="ignore", env_prefix=ENV_PREFIX)

    @classmethod
    def env_seeded_fields(cls) -> frozenset[str]:
        """Fields the environment sets through a default factory, not a source."""
        if os.environ.get(ENV_REDIS_URL):
            return frozenset({"broker_url", "result_backend"})
        return frozenset()

    broker_url: str = Field(
        default_factory=lambda: _redis_from_env(DEFAULT_BROKER_URL),
        json_schema_extra=_CELERY_RESTART,
    )
    result_backend: str = Field(
        default_factory=lambda: _redis_from_env(DEFAULT_RESULT_BACKEND),
        json_schema_extra=_CELERY_RESTART,
    )
    task_default_queue: str = Field(default=DEFAULT_QUEUE, json_schema_extra=_CELERY_RESTART)

    # ── Routing (GH #447) ───────────────────────────────────
    # Applied over every module's ``task_config.TASK_ROUTES``. Lets an operator
    # re-route a task (``{"reports.*": "heavy"}``) without a code change.
    task_routes_override: dict[str, Any] = Field(
        default_factory=dict,
        description="Task route overrides, {pattern: queue or route dict}.",
        json_schema_extra=_CELERY_RESTART,
    )

    # ── Worker tuning (GH #448) ─────────────────────────────
    # ``None`` keeps Celery's own default. Workers read these once at start.
    visibility_timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Redis visibility timeout. With acks_late, tasks running longer than "
            "this (Celery default 1 h) are redelivered and run twice."
        ),
        json_schema_extra=_CELERY_RESTART,
    )
    worker_max_tasks_per_child: int | None = Field(
        default=None, ge=1, json_schema_extra=_CELERY_RESTART
    )
    worker_max_memory_per_child_kb: int | None = Field(
        default=None, ge=1, json_schema_extra=_CELERY_RESTART
    )
    task_reject_on_worker_lost: bool | None = Field(default=None, json_schema_extra=_CELERY_RESTART)
    task_soft_time_limit: int | None = Field(default=None, ge=1, json_schema_extra=_CELERY_RESTART)
    task_time_limit: int | None = Field(default=None, ge=1, json_schema_extra=_CELERY_RESTART)
    worker_concurrency: int | None = Field(default=None, ge=1, json_schema_extra=_CELERY_RESTART)
    # Raw Celery conf (``SM_BG_TASKS_CELERY_OVERRIDES``, JSON) is deliberately NOT
    # a field here: every field is stored in and hydrated from the database, and
    # a DB-writable conf dict could switch serializers to pickle. It is read
    # from the environment only, in ``config_guards.celery_overrides_from_env``.

    # The per-worker module subset (``SM_BG_TASKS_WORKER_QUEUES`` /
    # ``_INCLUDE_MODULES`` / ``_EXCLUDE_MODULES``, GH #450) is likewise not a
    # field: it describes one process, so it is read from the environment only
    # in ``config_guards.worker_scope_from_env``.

    @field_validator("broker_url", "result_backend")
    @classmethod
    def _plain_url_scheme(cls, value: str, info: ValidationInfo) -> str:
        # Celery/kombu resolve a dotted or ``mod:Class`` scheme (or a bare
        # dotted backend name) by importing it, so a DB-stored URL must name a
        # transport/backend by plain alias only.
        scheme = value.split("://", 1)[0] if "://" in value else value
        if any(ch in scheme for ch in ".:/"):
            raise ValueError(
                f"{info.field_name} must use a plain URL scheme (redis://, amqp://, db+sqlite://); "
                "dotted or module:Class names are refused because Celery imports them"
            )
        return value

    @field_validator("task_routes_override", mode="before")
    @classmethod
    def _vet_task_routes(cls, value: object) -> object:
        # Admin-editable: the settings UI submits a JSON string. Parse it and
        # refuse (422) anything that is not a safe route mapping, rather than
        # saving a row that is silently dropped later. ``build_celery`` still
        # sanitises, as a defence for values stored before this check.
        return parse_task_routes(value)

    # ── Cross-process cache invalidation (GH #318) ──────────
    # This module owns the Redis connection, so it installs the transport that
    # carries the framework InvalidationBus between workers. Off means every
    # per-process cache — ``users``' revocation counter above all — stays stale
    # in the *other* workers until its own TTL expires, which is the behaviour
    # that predates the transport. Left on by default because a deployment with
    # Redis configured is the one that has several workers to keep in step; the
    # test suite turns it off, having no Redis to reach.
    broadcast_invalidations: bool = Field(
        default=True, json_schema_extra={"requires_restart": True, "group": "Celery"}
    )
    invalidation_channel: str = Field(
        default=DEFAULT_INVALIDATION_CHANNEL,
        min_length=1,
        json_schema_extra={"requires_restart": True, "group": "Celery"},
    )

    # Run tasks synchronously inside the calling process. Tests flip it on via
    # ``SM_BG_TASKS_TASK_ALWAYS_EAGER`` or by passing it explicitly, either of
    # which works without DB-backed hydration (which never fires for suites
    # that don't use the FastAPI lifespan).
    task_always_eager: bool = False
    task_eager_propagates: bool = True

    # A task that has been ``running`` longer than this without a heartbeat is
    # flipped to ``stuck`` by the beat sweep. 5 min is long enough to cover
    # normal slow jobs while still surfacing wedged workers within one UI
    # refresh.
    stuck_after_seconds: int = DEFAULT_STUCK_AFTER_SECONDS
    stuck_sweep_interval_seconds: int = DEFAULT_STUCK_SWEEP_INTERVAL_SECONDS
    purge_interval_seconds: int = DEFAULT_PURGE_INTERVAL_SECONDS

    retention_days: int = Field(
        default=DEFAULT_RETENTION_DAYS,
        ge=1,
        le=3650,
        description="Days to keep terminal task execution records (1-3650).",
    )
    max_retries: int = Field(
        default=DEFAULT_MAX_RETRIES,
        ge=0,
        le=100,
        description="Configured retry ceiling; individual tasks define their own policies (0-100).",
    )

    @field_validator("task_time_limit")
    @classmethod
    def _soft_limit_below_hard(cls, hard: int | None, info: ValidationInfo) -> int | None:
        """A soft limit at or above the hard one can never fire (#548).

        Attached to the later-declared hard limit so the error carries that
        field's ``loc`` and the settings form shows it under the field. It names
        the soft limit as related so boot hydration can drop a stored soft limit
        when the hard one is pinned by env.
        """
        soft = info.data.get("task_soft_time_limit")
        if hard is not None and soft is not None and soft >= hard:
            raise PydanticCustomError(
                "time_limit_order",
                "task_time_limit ({hard}) must be greater than task_soft_time_limit ({soft}); "
                "otherwise the soft limit can never fire",
                {"hard": hard, "soft": soft, RELATED_FIELDS_CTX: ["task_soft_time_limit"]},
            )
        return hard
