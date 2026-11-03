"""The wizard locks and migrates the app DB; CLI retains env fallback (#782)."""

import asyncio
import contextlib
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from alembic import command
from alembic.config import Config
from simple_module_hosting.setup_wizard import migrate
from sqlalchemy.ext.asyncio import create_async_engine

_ROOT = Path(__file__).resolve().parents[3]
_ENVS = [
    _ROOT / "host/migrations/env.py",
    _ROOT / "framework/cli/simple_module_cli/templates/host/migrations/env.py",
]


@pytest.mark.parametrize("env_path", _ENVS, ids=["host", "scaffold"])
@pytest.mark.parametrize("wizard", [True, False], ids=["wizard", "cli"])
async def test_migration_target(tmp_path, monkeypatch, env_path, wizard) -> None:
    app_db, env_db = tmp_path / "app.db", tmp_path / "env.db"
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{env_db}")
    scripts = tmp_path / "migrations"
    (scripts / "versions").mkdir(parents=True)
    (scripts / "env.py").write_text(env_path.read_text())
    (scripts / "versions/initial.py").write_text(
        "from alembic import op\nimport sqlalchemy as sa\n"
        'revision = "initial"\ndown_revision = None\n'
        'def upgrade():\n    op.create_table("marker", sa.Column("id", sa.Integer))\n'
        'def downgrade():\n    op.drop_table("marker")\n'
    )
    ini = tmp_path / "alembic.ini"
    ini.write_text(
        f"[alembic]\nscript_location = {scripts}\n"
        "[loggers]\nkeys=root\n[handlers]\nkeys=\n[formatters]\nkeys=\n"
        "[logger_root]\nlevel=WARNING\nhandlers=\n"
    )
    locked = []

    async def inline_thread(func, *args):
        return func(*args)

    monkeypatch.setattr(asyncio, "to_thread", inline_thread)

    @contextlib.contextmanager
    def lock(url):
        locked.append(url)
        yield

    monkeypatch.setattr(migrate, "migration_lock", lock)
    monkeypatch.setattr(migrate, "run_deferred_startup", AsyncMock())
    monkeypatch.setattr("simple_module_hosting.migrations.default_alembic_ini", lambda: str(ini))
    monkeypatch.setattr("simple_module_hosting.migrations.migration_status", AsyncMock())
    engine = create_async_engine(f"sqlite+aiosqlite:///{app_db}")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(sm=SimpleNamespace(db=SimpleNamespace(engine=engine)))
        ),
        state=SimpleNamespace(),
    )
    try:
        if wizard:
            await migrate.apply_migrations(request, {})
            assert locked == [engine.url]
        else:
            await asyncio.to_thread(command.upgrade, Config(str(ini)), "heads")
        for path, migrated in [(app_db, wizard), (env_db, not wizard)]:
            with contextlib.closing(sqlite3.connect(path)) as db:
                tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master")}
            assert ("alembic_version" in tables) is migrated
            assert ("marker" in tables) is migrated
    finally:
        await engine.dispose()
