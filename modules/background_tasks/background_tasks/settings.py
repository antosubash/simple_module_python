"""BackgroundTasks module settings (DB-backed).

Values come from defaults at boot, then get hydrated from the DB by the
hosting lifespan before module ``on_startup`` runs. Runtime changes go
through ``settings.reload.apply_changes_and_reload``.

The broker and result-backend URLs are deployment plumbing rather than module
config, so they stay env-readable through ``SM_REDIS_URL`` — one variable that
seeds both. They have to work *before* any DB row exists: the production
validator below rejects the localhost defaults, so without them a containerised
app can't boot far enough to hydrate settings, and a worker process (which
never sees ``app.state``) has no other source at all. Like every env var it
beats a stored value (env → DB → default): ``env_seeded_fields`` reports both
fields to the hydrator, since ``SM_REDIS_URL`` is read by their default
factories where pydantic's env source cannot see it. With it unset, the two
fields keep separate DB overrides for anyone who wants the broker and the
backend on different Redis databases.

``SM_BG_TASKS_BROKER_URL`` and ``SM_BG_TASKS_RESULT_BACKEND`` still work and
take precedence over ``SM_REDIS_URL`` — a deployment that set them meant them —
but log a deprecation warning. Being real env reads, they also beat a stored
value (env → DB → default, GH #486). They are answered by pydantic's own env source
now that ``env_prefix`` is set (GH #283), which is also what stops every other
field being readable from its bare, unprefixed name.

The other env read is ``SM_ENVIRONMENT``, consulted by the
``@model_validator`` to refuse a localhost broker in production — that's a
host-level setting, not a background_tasks-module field.

Process wiring, including ``outbox_mode`` and sweep cadence, requires a restart;
``json_schema_extra`` exposes that requirement in the settings UI.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_core import PydanticCustomError
from simple_module_core.settings_hydrate import RELATED_FIELDS_CTX

from background_tasks.constants import (
    DEFAULT_OUTBOX_LEASE_SECONDS,
    DEFAULT_OUTBOX_MAX_ATTEMPTS,
    DEFAULT_OUTBOX_SWEEP_INTERVAL_SECONDS,
    DEFAULT_RETENTION_DAYS,
    ENV_PREFIX,
    max_outbox_handler_timeout,
)
from background_tasks.settings_celery import _CELERY_RESTART, CelerySettingsFields
from background_tasks.settings_env_checks import (
    forbid_localhost_broker_in_production,
    warn_on_legacy_redis_vars,
)
from background_tasks.tracking import TrackingMode

__all__ = ["DEFAULT_RETENTION_DAYS", "ENV_PREFIX", "BackgroundTasksSettings"]

logger = logging.getLogger(__name__)


class BackgroundTasksSettings(CelerySettingsFields):
    """Configuration for the Celery + Redis task runner."""

    execution_tracking: TrackingMode = Field(
        default=TrackingMode.FULL, json_schema_extra=_CELERY_RESTART
    )
    track_publish: bool = Field(default=True, json_schema_extra=_CELERY_RESTART)

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        # Tracking controls are DB-backed; preserve env wiring for older fields.
        def db_only(source):
            def read():
                return {
                    k: v
                    for k, v in source().items()
                    if k not in {"execution_tracking", "track_publish"}
                }

            return read

        return (
            init_settings,
            db_only(env_settings),
            db_only(dotenv_settings),
            db_only(file_secret_settings),
        )

    # ── Durable event outbox (GH #459) ──────────────────────
    outbox_mode: Literal["celery", "inprocess"] = Field(
        default="celery", json_schema_extra=_CELERY_RESTART
    )
    outbox_max_attempts: int = Field(
        default=DEFAULT_OUTBOX_MAX_ATTEMPTS,
        ge=1,
        le=100,
        description="Delivery attempts before a durable event is marked dead (1-100).",
    )
    outbox_sweep_interval_seconds: int = Field(
        default=DEFAULT_OUTBOX_SWEEP_INTERVAL_SECONDS,
        ge=1,
        json_schema_extra=_CELERY_RESTART,
    )
    outbox_lease_seconds: int = Field(
        default=DEFAULT_OUTBOX_LEASE_SECONDS,
        ge=10,
        le=86400,
        description="Seconds a claimed delivery may run before another worker reclaims it.",
    )
    # Empty: the lease minus a safety margin (10 %, at least 5 s), the most allowed.
    outbox_handler_timeout_seconds: int | None = Field(
        default=None, ge=1, description="Seconds a durable handler may run per attempt."
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

    @field_validator("outbox_handler_timeout_seconds")
    @classmethod
    def _handler_timeout_fits_the_lease(
        cls, timeout: int | None, info: ValidationInfo
    ) -> int | None:
        """A handler outliving its lease would be reclaimed and run twice at once.

        A field validator (not a model one) so the error carries the field's
        ``loc`` and the settings form shows it under that field. The lease is
        declared first, so it is already in ``info.data`` unless it was invalid
        itself, in which case that error is the one to fix first.
        """
        lease = info.data.get("outbox_lease_seconds")
        if timeout is None or lease is None:
            return timeout
        ceiling = max_outbox_handler_timeout(lease)
        if timeout > ceiling:
            raise PydanticCustomError(
                "handler_timeout_exceeds_lease",
                "outbox_handler_timeout_seconds ({timeout}) must leave a safety margin "
                "inside outbox_lease_seconds ({lease}): at most "
                "{ceiling}. Raise the lease or lower the timeout.",
                {
                    "timeout": timeout,
                    "lease": lease,
                    "ceiling": f"{ceiling:g}",
                    RELATED_FIELDS_CTX: ["outbox_lease_seconds"],
                },
            )
        return timeout

    @model_validator(mode="after")
    def _check_broker_env(self) -> BackgroundTasksSettings:
        """Deprecation warnings and the production localhost-broker refusal."""
        warn_on_legacy_redis_vars(self.broker_url, self.result_backend)
        forbid_localhost_broker_in_production(self.broker_url, self.result_backend)
        return self
