"""The DB log sink: opt-in, task-correlated, redacted (GH #537)."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from background_tasks import log_sink, sync_db
from background_tasks.log_context import bind_task_context
from background_tasks.models import RetainedLog
from background_tasks.settings import BackgroundTasksSettings
from simple_module_db import tenant_context
from sqlalchemy import select

pytestmark = pytest.mark.usefixtures("sync_sqlite")

APP_LOGGER = logging.getLogger("bg_log_sink_test")


@pytest.fixture(autouse=True)
def _root_at_debug() -> Iterator[None]:
    root = logging.getLogger()
    before = root.level
    root.setLevel(logging.DEBUG)
    yield
    log_sink.uninstall_log_sink()
    root.setLevel(before)


def _rows() -> list[RetainedLog]:
    with sync_db.get_sync_session_factory()() as session:
        return list(session.execute(select(RetainedLog).order_by(RetainedLog.ts)).scalars())


def _enabled(**over: object) -> BackgroundTasksSettings:
    return BackgroundTasksSettings(log_sink_enabled=True, **over)


def test_disabled_by_default_writes_nothing():
    assert BackgroundTasksSettings().log_sink_enabled is False
    assert log_sink.install_log_sink(BackgroundTasksSettings()) is None
    APP_LOGGER.error("nobody keeps this")
    assert _rows() == []


def test_task_lines_carry_the_task_id():
    handler = log_sink.install_log_sink(_enabled())
    assert handler is not None
    with bind_task_context(task_id="celery-1", task_name="demo.task"):
        APP_LOGGER.info("inside the task")
    APP_LOGGER.info("outside")
    log_sink.uninstall_log_sink()
    by_message = {r.message: r for r in _rows() if r.logger == APP_LOGGER.name}
    assert by_message["inside the task"].task_id == "celery-1"
    assert by_message["inside the task"].extra["task_name"] == "demo.task"
    assert by_message["outside"].task_id is None


def test_level_threshold_and_level_number():
    log_sink.install_log_sink(_enabled(log_sink_level="WARNING"))
    APP_LOGGER.info("dropped")
    APP_LOGGER.error("kept")
    log_sink.uninstall_log_sink()
    rows = [r for r in _rows() if r.logger == APP_LOGGER.name]
    assert [(r.message, r.level) for r in rows] == [("kept", logging.ERROR)]


def test_secrets_never_reach_the_table():
    log_sink.install_log_sink(_enabled())
    APP_LOGGER.warning("calling with Authorization: Bearer abc.def.ghi and password=hunter2")
    log_sink.uninstall_log_sink()
    (row,) = [r for r in _rows() if r.logger == APP_LOGGER.name]
    assert "abc.def.ghi" not in row.message
    assert "hunter2" not in row.message


def test_tenant_is_stamped_and_long_messages_are_truncated():
    log_sink.install_log_sink(_enabled())
    with tenant_context("acme"):
        APP_LOGGER.info("x" * 10_000)
    log_sink.uninstall_log_sink()
    (row,) = [r for r in _rows() if r.logger == APP_LOGGER.name]
    assert row.tenant_id == "acme"
    assert len(row.message) == 4096


def test_exception_text_is_kept_and_redacted():
    log_sink.install_log_sink(_enabled())
    try:
        raise ValueError("password=hunter2")
    except ValueError:
        APP_LOGGER.exception("boom")
    log_sink.uninstall_log_sink()
    (row,) = [r for r in _rows() if r.logger == APP_LOGGER.name]
    assert "ValueError" in row.message
    assert "hunter2" not in row.message


def test_invalid_level_is_rejected():
    with pytest.raises(ValueError, match="log_sink_level"):
        BackgroundTasksSettings(log_sink_level="LOUD")
