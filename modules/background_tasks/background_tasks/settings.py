"""BackgroundTasks module settings (DB-backed).

Construction no longer reads ``SM_BG_TASKS_*`` environment variables. Values
come from pydantic defaults at boot, then get hydrated from the DB by the
hosting lifespan before module ``on_startup`` runs. Runtime changes go
through ``settings.reload.apply_changes_and_reload``.

The one remaining env read is ``SM_ENVIRONMENT``, consulted by the
``@model_validator`` to refuse a localhost broker in production — that's a
host-level setting, not a background_tasks-module field.

The Celery-critical fields (``broker_url``, ``result_backend``,
``task_default_queue``) are marked ``requires_restart=True`` via
``json_schema_extra`` because workers read these once at process start, so
DB changes can't be hot-reloaded: the admin UI should surface that bumping
these values requires a worker restart.
"""

from __future__ import annotations

import os

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.dotenv import env_bool
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
)

_CELERY_RESTART = {"requires_restart": True, "group": "Celery"}


class BackgroundTasksSettings(BaseSettings):
    """Configuration for the Celery + Redis task runner."""

    model_config = SettingsConfigDict(extra="ignore")

    broker_url: str = Field(default=DEFAULT_BROKER_URL, json_schema_extra=_CELERY_RESTART)
    result_backend: str = Field(default=DEFAULT_RESULT_BACKEND, json_schema_extra=_CELERY_RESTART)
    task_default_queue: str = Field(default=DEFAULT_QUEUE, json_schema_extra=_CELERY_RESTART)

    # Run tasks synchronously inside the calling process. Read at
    # module-import time so tests can flip it on via ``SM_BG_TASKS_*``
    # without going through DB-backed hydration (which never fires for
    # suites that don't use the FastAPI lifespan).
    task_always_eager: bool = env_bool("SM_BG_TASKS_TASK_ALWAYS_EAGER")
    task_eager_propagates: bool = True

    # A task that has been ``running`` longer than this without a heartbeat is
    # flipped to ``stuck`` by the beat sweep. 5 min is long enough to cover
    # normal slow jobs while still surfacing wedged workers within one UI
    # refresh.
    stuck_after_seconds: int = DEFAULT_STUCK_AFTER_SECONDS
    stuck_sweep_interval_seconds: int = DEFAULT_STUCK_SWEEP_INTERVAL_SECONDS
    purge_interval_seconds: int = DEFAULT_PURGE_INTERVAL_SECONDS

    retention_days: int = DEFAULT_RETENTION_DAYS
    max_retries: int = DEFAULT_MAX_RETRIES

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
            raise ValueError(
                f"{names} must not point at localhost when SM_ENVIRONMENT={env!r}. "
                "Set these to the Redis service host (e.g. redis://redis:6379/0)."
            )
        return self
