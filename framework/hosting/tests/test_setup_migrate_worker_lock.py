"""Independent wizard workers must serialize even on a fresh database (#634)."""

import asyncio
import importlib.util
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from alembic import command
from simple_module_hosting.setup_wizard import migrate
from simple_module_hosting.setup_wizard._migration_lock import migration_lock
from sqlalchemy.engine import make_url


def test_independent_workers_serialize_migrations(monkeypatch, tmp_path):
    # Separate module globals reproduce workers with distinct asyncio locks.
    spec = importlib.util.spec_from_file_location("other_worker", migrate.__file__)
    other = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(other)
    active = maximum = 0
    guard = threading.Lock()
    ready = threading.Barrier(2)

    def upgrade(config, target):
        nonlocal active, maximum
        assert target == "heads"
        with guard:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.1)
        with guard:
            active -= 1

    async def inline_thread(func):
        ready.wait(timeout=5)
        return func()

    monkeypatch.setattr(asyncio, "to_thread", inline_thread)
    monkeypatch.setattr(command, "upgrade", upgrade)
    monkeypatch.setattr("simple_module_hosting.migrations.migration_status", AsyncMock())
    monkeypatch.setattr(migrate, "run_deferred_startup", AsyncMock())
    monkeypatch.setattr(other, "run_deferred_startup", AsyncMock())
    url = make_url(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")

    def request():
        return SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    sm=SimpleNamespace(db=SimpleNamespace(engine=SimpleNamespace(url=url)))
                )
            ),
            state=SimpleNamespace(),
        )

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [
            workers.submit(asyncio.run, worker.apply_migrations(request(), {}))
            for worker in [migrate, other]
        ]
        for future in futures:
            future.result(timeout=5)
    assert maximum == 1


def test_sqlite_migration_lock_released_on_failure(tmp_path):
    url = make_url(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    with pytest.raises(RuntimeError, match="migration failed"), migration_lock(url):
        raise RuntimeError("migration failed")
    # Reacquiring on another connection must work after an exception.
    with migration_lock(url):
        pass
