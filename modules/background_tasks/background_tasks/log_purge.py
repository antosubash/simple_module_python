"""Retention for retained log lines (GH #537)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from background_tasks.constants import DEFAULT_LOG_RETENTION_DAYS, MODULE_NAME
from background_tasks.models import RetainedLog
from background_tasks.settings import BackgroundTasksSettings
from background_tasks.worker_settings import settings_for

logger = logging.getLogger(__name__)


def log_retention_days() -> int:
    """The DB-backed ``log_retention_days``; the default when settings are unreadable."""
    try:
        return settings_for(BackgroundTasksSettings, MODULE_NAME).log_retention_days
    except Exception:
        logger.warning("Could not read log_retention_days; using the default", exc_info=True)
        return DEFAULT_LOG_RETENTION_DAYS


def purge_log_records(session: Session, days: int | None = None) -> int:
    """Delete log lines older than ``days`` (the setting when omitted); returns the count."""
    cutoff = datetime.now(UTC) - timedelta(days=days if days is not None else log_retention_days())
    result = session.execute(delete(RetainedLog).where(RetainedLog.ts < cutoff))  # ty: ignore[invalid-argument-type]
    return result.rowcount or 0
