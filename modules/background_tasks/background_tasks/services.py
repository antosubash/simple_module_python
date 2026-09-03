"""Module-scoped state container for background_tasks.

Stored as ``app.state.background_tasks`` by
:meth:`BackgroundTasksModule.register_settings`. Not frozen — ``on_startup``
populates :attr:`celery` once the Celery app is built. Convention: set once
during boot, treat as read-only after.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from celery import Celery

    from background_tasks.contracts.schemas import WorkerSnapshot
    from background_tasks.settings import BackgroundTasksSettings


@dataclass
class BackgroundTasksServices:
    """BackgroundTasks singletons. Single slot at ``app.state.background_tasks``."""

    settings: BackgroundTasksSettings
    celery: Celery | None = None
    # The most recent fleet poll, kept so a screen that only wants to *mention*
    # the workers (Doctor's dev-server panel) can read one without paying the
    # ~1s inspect timeout itself. Written by whoever last polled; ``None``
    # until something has. Read it for reporting, never as a live reading —
    # ``polled_at`` says how old it is.
    last_worker_snapshot: WorkerSnapshot | None = None
