"""Execution tracking policy, resolved without database access."""

from enum import StrEnum
from typing import Any

from celery import current_app

from background_tasks.constants import INTERNAL_TASK_SWEEP_OUTBOX, SM_TRACKING_HEADER, TaskStatus
from background_tasks.tenant_context import _header_of_request


class TrackingMode(StrEnum):
    FULL = "full"
    TERMINAL = "terminal"
    FAILURES = "failures"
    OFF = "off"


def tracking_mode(
    *, task: Any = None, request: Any = None, headers: dict | None = None, name: str = ""
) -> TrackingMode:
    """Message override → task option → frozen application default."""
    app = getattr(task, "app", None) or current_app
    if task is None or isinstance(task, str):
        task = app.tasks.get(name or task)
    request = request if request is not None else getattr(task, "request", None)
    explicit = (headers or {}).get(SM_TRACKING_HEADER)
    if explicit is None:
        explicit = _header_of_request(request, SM_TRACKING_HEADER)
    value = explicit if explicit is not None else getattr(task, SM_TRACKING_HEADER, None)
    # Publishers may not have imported the internal task registration yet.
    if value is None and name == INTERNAL_TASK_SWEEP_OUTBOX:
        value = TrackingMode.FAILURES
    if value is None:
        value = app.conf.get("sm_execution_tracking", TrackingMode.FULL)
    try:
        return TrackingMode(value)
    except (ValueError, TypeError):
        # A malformed override must not hide failures from operators.
        return TrackingMode.FULL


def records_signal(mode: TrackingMode, handler: str, status: Any, *, app: Any) -> bool:
    if mode == TrackingMode.FULL:
        return handler != "on_task_publish" or app.conf.get("sm_track_publish", True)
    if mode == TrackingMode.OFF:
        return False
    return status in (
        {TaskStatus.FAILED, TaskStatus.REVOKED, TaskStatus.SUCCESS}
        if mode == TrackingMode.TERMINAL
        else {TaskStatus.FAILED, TaskStatus.REVOKED}
    )
