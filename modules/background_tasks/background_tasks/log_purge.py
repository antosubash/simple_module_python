"""Retention for retained log lines (GH #537)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from background_tasks.models import RetainedLog


def purge_log_records(session: Session, cutoff: datetime) -> int:
    """Delete log lines older than ``cutoff``; returns the count."""
    result = session.execute(delete(RetainedLog).where(RetainedLog.ts < cutoff))  # ty: ignore[invalid-argument-type]
    return result.rowcount or 0
