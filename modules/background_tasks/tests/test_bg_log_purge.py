"""Retention for retained log lines (GH #537)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from background_tasks import log_purge, sync_db, tasks
from background_tasks.models import RetainedLog
from background_tasks.settings import BackgroundTasksSettings
from sqlalchemy import select

pytestmark = pytest.mark.usefixtures("sync_sqlite")


def _seed(*ages_days: int) -> None:
    now = datetime.now(UTC)
    with sync_db.sync_session() as session:
        for i, age in enumerate(ages_days):
            session.add(
                RetainedLog(
                    ts=now - timedelta(days=age), level=20, logger="t", message=f"{age}d #{i}"
                )
            )


def _messages() -> set[str]:
    with sync_db.sync_session() as session:
        return set(session.execute(select(RetainedLog.message)).scalars())


def test_purge_removes_rows_older_than_retention():
    _seed(1, 6, 8, 30)
    with sync_db.sync_session() as session:
        assert log_purge.purge_log_records(session, datetime.now(UTC) - timedelta(days=7)) == 2
    assert _messages() == {"1d #0", "6d #1"}


def test_purge_old_executions_applies_the_setting(monkeypatch):
    monkeypatch.setattr(
        tasks, "load_runner_settings", lambda: BackgroundTasksSettings(log_retention_days=3)
    )
    _seed(1, 5)
    assert tasks.purge_old_executions() == 1
    assert _messages() == {"1d #0"}
