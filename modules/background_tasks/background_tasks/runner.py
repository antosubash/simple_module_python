"""Build the Celery app for a worker or beat process.

The repo's ``scripts/run_worker.py`` and the one ``smpy new`` scaffolds both
call :func:`build_runner_celery`. They used to carry their own copies of this
bootstrap, and the scaffolded copy fell behind: it built Celery from the
environment alone, so a generated app's worker ignored settings saved in the
admin UI and could read a different ``.env`` from the web process (GH #490).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.dotenv import find_env_file, load_dotenv_into_environ

if TYPE_CHECKING:
    from celery import Celery

_PROJECT_ROOT = "SM_PROJECT_ROOT"


def _load_env(fallback_env_file: Path | None) -> None:
    """Load ``.env`` the way the web process resolves it.

    ``find_env_file`` (SM_PROJECT_ROOT, then a bounded walk-up) keeps the worker
    and the web process on the same file. ``fallback_env_file`` applies only
    when that resolves to no file at all — celery launched from an unrelated
    cwd, possibly inside some other checkout, with SM_PROJECT_ROOT unset. It is
    adopted by setting SM_PROJECT_ROOT rather than by loading the file directly,
    so every later reader (``BootstrapSettings``' sqlite anchor, the host
    settings' ``.env`` scan) resolves the same project instead of the cwd.
    """
    env_file = find_env_file()
    if (
        fallback_env_file is not None
        and _PROJECT_ROOT not in os.environ
        and not env_file.is_file()
        and fallback_env_file.is_file()
    ):
        os.environ[_PROJECT_ROOT] = str(fallback_env_file.parent)
        env_file = find_env_file()
    load_dotenv_into_environ(env_file)


def build_runner_celery(fallback_env_file: Path | None = None) -> Celery:
    """``.env`` → host settings → DB-hydrated ``BackgroundTasksSettings`` → Celery."""
    _load_env(fallback_env_file)

    # Imported after ``.env`` is in the environment, so nothing below can
    # resolve a setting before it is.
    from simple_module_hosting import merge_host_settings
    from simple_module_hosting.leases import configure_process_leases

    from background_tasks.celery_app import build_celery
    from background_tasks.sync_db import set_database_url
    from background_tasks.tenant_context import set_default_tenant
    from background_tasks.worker_settings import load_runner_settings

    # The worker never builds the app, so resolve the host settings the same
    # way host/main.py does (env → DB → default): task bodies must hit the same
    # database with the same fail-closed tenant rules as request code.
    host = merge_host_settings()
    default_tenant = None if host.multi_tenant else host.default_tenant or None
    set_database_url(
        host.database_url, tenant_strict=host.multi_tenant, default_tenant=default_tenant
    )
    set_default_tenant(default_tenant)
    # Task bodies share the web process's leases (GH #539): same Redis or table.
    configure_process_leases(host.redis_url, database_url=host.database_url)
    # Hydrated from the DB like the web process, so an admin-edited setting
    # reaches the worker at boot, not only the web app.
    return build_celery(load_runner_settings())
