"""Retained-log settings (GH #537), split out of ``settings.py`` for size."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from background_tasks.constants import (
    DEFAULT_LOG_RETENTION_DAYS,
    DEFAULT_LOG_SINK_LEVEL,
    LOG_LEVEL_NAMES,
)


class LogSinkFields(BaseModel):
    """Fields mixed into ``BackgroundTasksSettings``."""

    # ── Retained logs (GH #537) ─────────────────────────────
    # Off by default: it writes a row per log line, which a deployment that
    # already ships logs elsewhere does not want. Handlers are installed at
    # process start, so changing these needs a restart of web and workers.
    log_sink_enabled: bool = Field(
        default=False,
        description="Keep application and task log lines in the database.",
        json_schema_extra={"requires_restart": True, "group": "Logs"},
    )
    log_sink_level: str = Field(
        default=DEFAULT_LOG_SINK_LEVEL,
        description="Lowest level kept (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
        json_schema_extra={"requires_restart": True, "group": "Logs"},
    )
    log_retention_days: int = Field(
        default=DEFAULT_LOG_RETENTION_DAYS,
        ge=1,
        le=3650,
        description="Days to keep retained log lines (1-3650).",
        json_schema_extra={"group": "Logs"},
    )

    @field_validator("log_sink_level")
    @classmethod
    def _known_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in LOG_LEVEL_NAMES:
            raise ValueError(f"log_sink_level must be one of {', '.join(LOG_LEVEL_NAMES)}")
        return level
