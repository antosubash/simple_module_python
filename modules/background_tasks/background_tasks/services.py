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

    from background_tasks.settings import BackgroundTasksSettings


@dataclass
class BackgroundTasksServices:
    """BackgroundTasks singletons. Single slot at ``app.state.background_tasks``."""

    settings: BackgroundTasksSettings
    celery: Celery | None = None
