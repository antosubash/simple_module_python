"""BackgroundTasks module settings (DB-backed).

Values come from defaults at boot, then get hydrated from the DB by the
hosting lifespan before module ``on_startup`` runs. Runtime changes go
through ``settings.reload.apply_changes_and_reload``.

The broker and result-backend URLs are deployment plumbing rather than module
config, so they stay env-readable through ``SM_REDIS_URL`` — one variable that
seeds both. They have to work *before* any DB row exists: the production
validator below rejects the localhost defaults, so without them a containerised
app can't boot far enough to hydrate settings, and a worker process (which
never sees ``app.state``) has no other source at all. A DB value still wins
once hydration runs, and the two fields keep separate overrides for anyone who
wants the broker and the backend on different Redis databases.

``SM_BG_TASKS_BROKER_URL`` and ``SM_BG_TASKS_RESULT_BACKEND`` still work and
take precedence over ``SM_REDIS_URL`` — a deployment that set them meant them —
but log a deprecation warning. They are answered by pydantic's own env source
now that ``env_prefix`` is set (GH #283), which is also what stops every other
field being readable from its bare, unprefixed name.

The other env read is ``SM_ENVIRONMENT``, consulted by the
``@model_validator`` to refuse a localhost broker in production — that's a
host-level setting, not a background_tasks-module field.

The Celery-critical fields (``broker_url``, ``result_backend``,
``task_default_queue``) are marked ``requires_restart=True`` via
``json_schema_extra`` because workers read these once at process start, so
DB changes can't be hot-reloaded: the admin UI should surface that bumping
these values requires a worker restart.
"""

from __future__ import annotations

import logging
import os

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.environments import NON_PROD_ENVIRONMENTS

from background_tasks.constants import (
    DEFAULT_BROKER_URL,
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

_CELERY_RESTART = {"requires_restart": True, "group": "Celery"}

logger = logging.getLogger(__name__)


def _redis_from_env(default: str) -> str:
    """``SM_REDIS_URL`` → the module default.

    ``env_prefix`` means pydantic's env source has already answered
    ``SM_BG_TASKS_BROKER_URL`` / ``SM_BG_TASKS_RESULT_BACKEND`` by the time a
    default is needed, so this factory is only the ``SM_REDIS_URL`` half — the
    legacy names keep working, and keep winning, through that source instead.
    """
    return os.environ.get(ENV_REDIS_URL) or default


class BackgroundTasksSettings(BaseSettings):
    """Configuration for the Celery + Redis task runner."""

    # Without ``env_prefix`` pydantic-settings resolves each field from its
    # bare, case-insensitive name — so a container setting ``broker_url`` or
    # ``retention_days`` for any other purpose silently reconfigured Celery,
    # and the documented ``SM_BG_TASKS_*`` names did nothing (GH #283).
    model_config = SettingsConfigDict(extra="ignore", env_prefix=ENV_PREFIX)

    broker_url: str = Field(
        default_factory=lambda: _redis_from_env(DEFAULT_BROKER_URL),
        json_schema_extra=_CELERY_RESTART,
    )
    result_backend: str = Field(
        default_factory=lambda: _redis_from_env(DEFAULT_RESULT_BACKEND),
        json_schema_extra=_CELERY_RESTART,
    )
    task_default_queue: str = Field(default=DEFAULT_QUEUE, json_schema_extra=_CELERY_RESTART)

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

    @model_validator(mode="after")
    def _warn_on_legacy_redis_vars(self) -> BackgroundTasksSettings:
        """Nudge deployments off the per-field names onto ``SM_REDIS_URL``.

        Warns rather than failing: ``smpy_gis``, ``smpy_saas``,
        ``laco_wiki_python`` and the ``nodes-k8s`` manifests all set these, and
        breaking them on upgrade buys nothing. It lives here rather than in the
        default factory because ``env_prefix`` means the env source answers
        these names before any default is consulted, so the factory never sees
        them.
        """
        for field, legacy_var in (
            ("broker_url", f"{ENV_PREFIX}BROKER_URL"),
            ("result_backend", f"{ENV_PREFIX}RESULT_BACKEND"),
        ):
            if os.environ.get(legacy_var) == getattr(self, field):
                logger.warning(
                    "%s is deprecated; use %s instead (one URL seeds both the "
                    "broker and the result backend).",
                    legacy_var,
                    ENV_REDIS_URL,
                )
        return self

    @model_validator(mode="after")
    def _forbid_localhost_broker_in_production(self) -> BackgroundTasksSettings:
        """Fail boot if production is still pointed at the dev default broker.

        A localhost broker in prod means the web container is talking to its
        own 6379 instead of the shared Redis service — tasks would silently
        queue to a broker no worker reads.
        """
        env = os.environ.get("SM_ENVIRONMENT", "development")
        if env in NON_PROD_ENVIRONMENTS:
            return self
        bad = []
        if "localhost" in self.broker_url or "127.0.0.1" in self.broker_url:
            bad.append("broker_url")
        if "localhost" in self.result_backend or "127.0.0.1" in self.result_backend:
            bad.append("result_backend")
        if bad:
            names = ", ".join(bad)
            env_names = ", ".join(f"{ENV_PREFIX}{name.upper()}" for name in bad)
            raise ValueError(
                f"{names} must not point at localhost when SM_ENVIRONMENT={env!r}. "
                f"Set {ENV_REDIS_URL} on the container to the Redis service host "
                "(e.g. redis://redis:6379/0) — one URL seeds both the broker and "
                f"the result backend. ({env_names} still override it per field, "
                "but are deprecated.) These are read before the DB-backed "
                "settings exist, so an environment variable is what satisfies "
                "this at boot."
            )
        return self
