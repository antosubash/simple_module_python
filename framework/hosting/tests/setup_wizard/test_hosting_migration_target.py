"""The wizard locks and migrates the app DB; CLI retains env fallback (#782)."""

import asyncio
import contextlib
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from simple_module_core.web.setup_steps import SetupRegistry, SetupStep
from simple_module_hosting.pipeline.setup_gate import STEP_MIGRATIONS
from simple_module_hosting.setup_wizard import migrate
from sqlalchemy.ext.asyncio import create_async_engine

_ROOT = Path(__file__).resolve().parents[4]
_ENVS = [
    _ROOT / "host/migrations/env.py",
    _ROOT / "framework/cli/simple_module_cli/templates/host/migrations/env.py",
]


def _migration_registry():
    registry = SetupRegistry()
    registry.add(
        SetupStep(
            id=STEP_MIGRATIONS,
            title="Migrations",
            is_complete=AsyncMock(return_value=False),
        )
    )
    return registry


async def test_wizard_refuses_a_stamped_database_after_config_is_restored(tmp_path, monkeypatch):
    (tmp_path / "versions").mkdir()
    (tmp_path / "versions/upgraded.py").write_text("revision = 'upgraded'\ndown_revision = None\n")
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                sm=SimpleNamespace(
                    db=SimpleNamespace(engine=engine), setup_registry=_migration_registry()
                ),
                migration={"is_current": None, "current_revision": None},
            )
        ),
        state=SimpleNamespace(),
    )
    upgrade = Mock()
    monkeypatch.setattr(command, "upgrade", upgrade)
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32))")
            await conn.exec_driver_sql("INSERT INTO alembic_version VALUES ('legacy')")
        (tmp_path / "alembic.ini").write_text("[alembic]\nscript_location = %(here)s\n")
        with pytest.raises(HTTPException) as error:
            await migrate.apply_migrations(request, {})
        assert error.value.status_code == 409
        upgrade.assert_not_called()
    finally:
        await engine.dispose()


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

    @contextlib.contextmanager
    def lock(url):
        locked.append(url)
        yield

    monkeypatch.setattr(migrate, "migration_lock", lock)
    monkeypatch.setattr(migrate, "run_deferred_startup", AsyncMock())
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    engine = create_async_engine(f"sqlite+aiosqlite:///{app_db}")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                sm=SimpleNamespace(
                    db=SimpleNamespace(engine=engine), setup_registry=_migration_registry()
                )
            )
        ),
        state=SimpleNamespace(),
    )
    try:
        if wizard:
            result = await migrate.apply_migrations(request, {})
            assert result["migration"]["is_current"] is True
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


async def test_wizard_reports_missing_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    request = SimpleNamespace()
    with pytest.raises(HTTPException, match="No Alembic config") as error:
        await migrate.apply_migrations(request, {})
    assert error.value.status_code == 503
