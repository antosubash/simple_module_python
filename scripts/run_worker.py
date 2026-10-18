"""Entry point for the Celery worker and beat services.

Usage::

    uv run celery -A scripts.run_worker:celery worker -l info
    uv run celery -A scripts.run_worker:celery beat   -l info

Both the web process and the worker go through the same
:func:`background_tasks.celery_app.build_celery` factory, so the broker
config, autodiscovered tasks, and signal handlers stay in lockstep. The
bootstrap around it (``.env``, host settings, DB-hydrated module settings)
lives in :mod:`background_tasks.runner`, shared with scaffolded apps.
"""

from __future__ import annotations

from pathlib import Path

from background_tasks.runner import build_runner_celery

# Module-level name ``celery`` is what ``celery -A scripts.run_worker:celery``
# looks for. Keep it stable. The fallback is the repo-root ``.env`` (next to
# ``.env.example``, not under ``host/``).
celery = build_runner_celery(Path(__file__).resolve().parent.parent / ".env")
