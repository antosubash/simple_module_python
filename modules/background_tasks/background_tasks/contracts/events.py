"""Public events emitted by the BackgroundTasks module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from simple_module_core.events import Event


@dataclass
class TaskFailed(Event):
    """A task transitioned to ``failed`` — subscribers may alert/log."""

    task_execution_id: uuid.UUID
    task_name: str
    exception_type: str | None


@dataclass
class TaskRetried(Event):
    """A failed/stuck task was manually retried via the admin UI."""

    original_id: uuid.UUID
    new_id: uuid.UUID
    task_name: str
