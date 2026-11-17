"""Independent wizard workers must serialize even on a fresh database (#634)."""

import asyncio
import importlib.util
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from alembic import command
from fastapi import HTTPException
from simple_module_core.setup_steps import SetupRegistry, SetupStep
from simple_module_hosting.setup_gate import STEP_MIGRATIONS
from simple_module_hosting.setup_wizard import migrate
from simple_module_hosting.setup_wizard._migration_lock import migration_lock
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


def test_independent_workers_serialize_migrations(monkeypatch, tmp_path):
    # Separate module globals reproduce workers with distinct asyncio locks.
    spec = importlib.util.spec_from_file_location("other_worker", migrate.__file__)
    other = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(other)
    applied = []
    ready = threading.Barrier(2)
    database = tmp_path / "fresh.db"
    url = f"sqlite+aiosqlite:///{database}"
    (tmp_path / "versions").mkdir()
    (tmp_path / "versions/initial.py").write_text("revision = 'initial'\ndown_revision = None\n")
    (tmp_path / "alembic.ini").write_text("[alembic]\nscript_location = %(here)s\n")
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))

    def upgrade(config, target):
        assert target == "heads"
        applied.append(target)
        with closing(sqlite3.connect(database)) as conn, conn:
            conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
            conn.execute("INSERT INTO alembic_version VALUES ('initial')")

    monkeypatch.setattr(command, "upgrade", upgrade)
    monkeypatch.setattr(migrate, "run_deferred_startup", AsyncMock())
    monkeypatch.setattr(other, "run_deferred_startup", AsyncMock())

    async def run(worker):
        engine = create_async_engine(url)
        registry = SetupRegistry()
        registry.add(
            SetupStep(
                id=STEP_MIGRATIONS, title="Migrations", is_complete=AsyncMock(return_value=False)
            )
        )
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    sm=SimpleNamespace(db=SimpleNamespace(engine=engine), setup_registry=registry)
                )
            ),
            state=SimpleNamespace(),
        )
        try:
            await asyncio.to_thread(ready.wait, 5)
            result = await worker.apply_migrations(request, {})
            assert result["migration"]["is_current"] is True
            return 200
        except HTTPException as exc:
            return exc.status_code
        finally:
            await engine.dispose()

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(asyncio.run, run(worker)) for worker in [migrate, other]]
        assert sorted(future.result(timeout=5) for future in futures) == [200, 409]
    assert applied == ["heads"]


def test_sqlite_migration_lock_released_on_failure(tmp_path):
    url = make_url(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    with pytest.raises(RuntimeError, match="migration failed"), migration_lock(url):
        raise RuntimeError("migration failed")
    # Reacquiring on another connection must work after an exception.
    with migration_lock(url):
        pass
