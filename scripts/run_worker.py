"""Entry point for the Celery worker and beat services.

Usage::

    uv run celery -A scripts.run_worker:celery worker -l info
    uv run celery -A scripts.run_worker:celery beat   -l info

Both the web process and the worker go through the same
:func:`background_tasks.celery_app.build_celery` factory, so the broker
config, autodiscovered tasks, and signal handlers stay in lockstep.
"""

from __future__ import annotations

from background_tasks.celery_app import build_celery
from background_tasks.settings import BackgroundTasksSettings

# Module-level name ``celery`` is what ``celery -A scripts.run_worker:celery``
# looks for. Keep it stable.
celery = build_celery(BackgroundTasksSettings())
