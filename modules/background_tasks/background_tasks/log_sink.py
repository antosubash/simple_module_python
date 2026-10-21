"""The database log sink and its installer (GH #537).

``DbLogSink`` writes batches through the worker-style sync session, so it works
the same in the web process and in a Celery child, and never touches a request
transaction. Installation is idempotent and fork-aware: a prefork child inherits
the parent's handler but not its listener thread, so ``worker_process_init``
replaces it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from celery.signals import worker_process_init
from simple_module_db import current_tenant_id
from simple_module_hosting.log_sinks import QueueSinkHandler, install_sink, uninstall_sink

from background_tasks.constants import (
    LOG_EXTRA_MAX_KEYS,
    LOG_EXTRA_VALUE_MAX_LENGTH,
    LOG_ID_MAX_LENGTH,
    LOG_MESSAGE_MAX_LENGTH,
    LOG_NAME_MAX_LENGTH,
    TENANT_ID_MAX_LENGTH,
)
from background_tasks.log_context import LogContextFilter
from background_tasks.models import RetainedLog
from background_tasks.settings import BackgroundTasksSettings
from background_tasks.sync_db import sync_session

_log = logging.getLogger(__name__)

_COLUMN_ATTRS = ("task_id", "job_id", "tenant_id", "correlation_id")
_STANDARD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
_handler: QueueSinkHandler | None = None


def _text(value: object, limit: int) -> str | None:
    return None if value in (None, "") else str(value)[:limit]


def _extra(record: logging.LogRecord) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _STANDARD_ATTRS or key in _COLUMN_ATTRS:
            continue
        if len(extra) >= LOG_EXTRA_MAX_KEYS:
            break
        extra[key[:LOG_NAME_MAX_LENGTH]] = (
            value
            if isinstance(value, bool | int | float)
            else str(value)[:LOG_EXTRA_VALUE_MAX_LENGTH]
        )
    return extra


def to_row(record: logging.LogRecord) -> RetainedLog:
    """Map an already-redacted ``LogRecord`` onto its table row."""
    return RetainedLog(
        ts=datetime.fromtimestamp(record.created, UTC),
        level=record.levelno,
        logger=record.name[:LOG_NAME_MAX_LENGTH],
        message=str(record.msg)[:LOG_MESSAGE_MAX_LENGTH],
        task_id=_text(getattr(record, "task_id", None), LOG_ID_MAX_LENGTH),
        job_id=_text(getattr(record, "job_id", None), LOG_ID_MAX_LENGTH),
        tenant_id=_text(getattr(record, "tenant_id", None), TENANT_ID_MAX_LENGTH),
        correlation_id=_text(getattr(record, "correlation_id", None), LOG_ID_MAX_LENGTH),
        extra=json.loads(json.dumps(_extra(record), default=str)),
    )


class DbLogSink:
    """``LogSink`` that inserts one ``RetainedLog`` row per record."""

    def emit_batch(self, records: Sequence[logging.LogRecord]) -> None:
        with sync_session() as session:
            session.add_all([to_row(r) for r in records])


class TenantStampFilter(logging.Filter):
    """Stamp the emitting context's tenant onto the record, before it is queued."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "tenant_id", None):
            record.tenant_id = current_tenant_id.get()
        return True


def install_log_sink(settings: BackgroundTasksSettings) -> QueueSinkHandler | None:
    """Install the DB sink on the root logger when enabled; replace any earlier one."""
    global _handler
    uninstall_log_sink()
    if not settings.log_sink_enabled:
        return None
    level = logging.getLevelNamesMapping()[settings.log_sink_level.upper()]
    handler = install_sink(DbLogSink(), level=level)
    # Handler filters run on the emitting thread, where the task's log context
    # and tenant are bound; the listener thread sees neither.
    handler.addFilter(LogContextFilter())
    handler.addFilter(TenantStampFilter())
    _handler = handler
    _log.info("Retained log sink installed (level=%s)", settings.log_sink_level)
    return handler


def uninstall_log_sink() -> None:
    global _handler
    handler, _handler = _handler, None
    if handler is not None:
        uninstall_sink(handler)


@worker_process_init.connect
def _reinstall_in_child(**_: object) -> None:
    """A forked child has the parent's handler but not its thread: build its own."""
    global _handler
    handler, _handler = _handler, None
    if handler is None:
        return
    logging.getLogger().removeHandler(handler)
    from background_tasks.worker_settings import load_runner_settings

    install_log_sink(load_runner_settings())
