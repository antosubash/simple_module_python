"""Entry point for the Celery worker and beat services.

Usage::

    uv run celery -A scripts.run_worker:celery worker -l info
    uv run celery -A scripts.run_worker:celery beat   -l info

Both the web process and the worker go through the same
:func:`background_tasks.celery_app.build_celery` factory, so the broker
config, autodiscovered tasks, and signal handlers stay in lockstep.
"""

from __future__ import annotations

from pathlib import Path

from simple_module_core.dotenv import find_env_file, load_dotenv_into_environ

# Match the precedence uvicorn gives the web process: load the repo-root
# ``.env`` into the environment before importing settings, so the worker
# doesn't fall back to defaults when celery is launched outside the repo cwd.
# Go through the shared resolution convention (SM_PROJECT_ROOT, then a
# bounded walk-up) so this worker and the web process can never disagree
# about which file is in effect. Only fall back to the hardcoded
# repo-root guess — ``.env`` next to ``.env.example``, not under ``host/``
# — when find_env_file() couldn't resolve anything more specific than a
# bare, nonexistent ``./.env`` (e.g. celery launched from an unrelated cwd
# with SM_PROJECT_ROOT unset).
_env_file = find_env_file()
if _env_file == Path(".env") and not _env_file.is_file():
    _env_file = Path(__file__).resolve().parent.parent / ".env"
load_dotenv_into_environ(_env_file)

from background_tasks.celery_app import build_celery  # noqa: E402
from background_tasks.settings import BackgroundTasksSettings  # noqa: E402

# Module-level name ``celery`` is what ``celery -A scripts.run_worker:celery``
# looks for. Keep it stable.
celery = build_celery(BackgroundTasksSettings())
