"""The retained log sink must not retain its own writes (BUG-001)."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator

import pytest
from background_tasks import log_sink, sync_db
from background_tasks.contracts.schemas import TaskExecutionDetail, TaskExecutionListItem
from background_tasks.models import RetainedLog
from background_tasks.settings import BackgroundTasksSettings
from sqlalchemy import func, select

pytestmark = pytest.mark.usefixtures("sync_sqlite")

APP_LOGGER = logging.getLogger("bg_log_sink_loop_test")


@pytest.fixture(autouse=True)
def _root_at_debug() -> Iterator[None]:
    root = logging.getLogger()
    db_logger = logging.getLogger("simple_module.db")
    before, db_before = root.level, db_logger.level
    root.setLevel(logging.DEBUG)
    db_logger.setLevel(logging.INFO)
    yield
    log_sink.uninstall_log_sink()
    root.setLevel(before)
    db_logger.setLevel(db_before)


def _count() -> int:
    with sync_db.get_sync_session_factory()() as session:
        return session.execute(select(func.count()).select_from(RetainedLog)).scalar_one()


def test_sink_writes_are_not_retained_again():
    handler = log_sink.install_log_sink(BackgroundTasksSettings(log_sink_enabled=True))
    assert handler is not None
    for i in range(5):
        APP_LOGGER.info("line %d", i)
    time.sleep(1.5)  # intentional-sleep: absence of feedback growth can only be observed over time
    first = _count()
    time.sleep(1.5)  # intentional-sleep: second observation window
    assert _count() == first
    log_sink.uninstall_log_sink()
    with sync_db.get_sync_session_factory()() as session:
        loggers = set(session.execute(select(RetainedLog.logger)).scalars())
    assert APP_LOGGER.name in loggers
    assert "simple_module.db" not in loggers


def test_null_args_and_kwargs_render():
    row = {"id": uuid.uuid4(), "task_name": "t", "status": "pending", "queue": "q", "retries": 0}
    assert TaskExecutionListItem(**row, args=None, kwargs=None).kwargs == {}
    detail = TaskExecutionDetail(**row, args=None, kwargs=None)
    assert detail.args == [] and detail.kwargs == {}
