"""BackgroundTasks module — Celery + Redis task queue with admin UI."""

from typing import TYPE_CHECKING, Any

from background_tasks.after_commit import enqueue_after_commit
from background_tasks.constants import SM_TRACKING_HEADER
from background_tasks.log_context import (
    bind_task_context,
    get_log_context,
    install_log_filter,
)
from background_tasks.task_resource import with_task_resource
from background_tasks.tracking import TrackingMode

if TYPE_CHECKING:
    from background_tasks.task_heartbeat import heartbeat
    from background_tasks.worker_settings import settings_for

_LAZY_HEARTBEAT = "heartbeat"
_LAZY_SETTINGS = "settings_for"


def __getattr__(name: str) -> Any:
    if name == _LAZY_HEARTBEAT:
        from background_tasks.task_heartbeat import heartbeat

        return heartbeat
    if name == _LAZY_SETTINGS:
        from background_tasks.worker_settings import settings_for

        return settings_for
    raise AttributeError(name)


__all__ = [
    "SM_TRACKING_HEADER",
    "TrackingMode",
    "bind_task_context",
    "enqueue_after_commit",
    "get_log_context",
    "heartbeat",
    "install_log_filter",
    "settings_for",
    "with_task_resource",
]
