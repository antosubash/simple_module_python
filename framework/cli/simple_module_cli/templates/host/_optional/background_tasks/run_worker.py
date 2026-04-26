"""Entry point for the Celery worker and beat services.

Both the web process and the worker go through the same
``background_tasks.celery_app.build_celery`` factory so the broker
config, autodiscovered tasks, and signal handlers stay in lockstep.

Run locally:
    uv run celery -A scripts.run_worker:celery worker -l info
    uv run celery -A scripts.run_worker:celery beat   -l info
"""

from __future__ import annotations

from background_tasks.celery_app import build_celery
from background_tasks.settings import BackgroundTasksSettings

celery = build_celery(BackgroundTasksSettings())
