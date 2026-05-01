"""Entry point for the Celery worker and beat services.

Both the web process and the worker go through the same
``background_tasks.celery_app.build_celery`` factory so the broker
config, autodiscovered tasks, and signal handlers stay in lockstep.

Run locally:
    uv run celery -A scripts.run_worker:celery worker -l info
    uv run celery -A scripts.run_worker:celery beat   -l info
"""

from __future__ import annotations

from pathlib import Path

from simple_module_core.dotenv import load_dotenv_into_environ

# Match the precedence uvicorn gives the web process: load ``.env`` into the
# environment before importing settings, so the worker doesn't fall back to
# SQLite defaults when celery is launched outside the host's cwd.
load_dotenv_into_environ(Path(__file__).resolve().parent.parent / ".env")

from background_tasks.celery_app import build_celery  # noqa: E402
from background_tasks.settings import BackgroundTasksSettings  # noqa: E402

celery = build_celery(BackgroundTasksSettings())
