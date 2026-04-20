"""BackgroundTasks module settings loaded from SM_BG_TASKS_* env vars."""

from __future__ import annotations

import os

from pydantic import model_validator
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
)


class BackgroundTasksSettings(BaseSettings):
    """Configuration for the Celery + Redis task runner."""

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, env_file=".env", extra="ignore")

    broker_url: str = DEFAULT_BROKER_URL
    result_backend: str = DEFAULT_RESULT_BACKEND
    task_default_queue: str = DEFAULT_QUEUE

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
            bad.append(f"{ENV_PREFIX}BROKER_URL")
        if "localhost" in self.result_backend or "127.0.0.1" in self.result_backend:
            bad.append(f"{ENV_PREFIX}RESULT_BACKEND")
        if bad:
            names = ", ".join(bad)
            raise ValueError(
                f"{names} must not point at localhost when SM_ENVIRONMENT={env!r}. "
                "Set these to the Redis service host (e.g. redis://redis:6379/0)."
            )
        return self
