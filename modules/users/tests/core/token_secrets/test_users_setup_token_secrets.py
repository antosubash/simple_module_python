"""Setup adopts one stored root for existing workers and subsequent boots."""

import sqlite3
import uuid
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from alembic import command
from auth.module import AuthModule
from fastapi_users.jwt import decode_jwt
from simple_module_core.setup_steps import SetupRegistry, SetupStep
from simple_module_hosting._app_boot import build_fastapi_app
from simple_module_hosting._preapp_config import merge_host_settings
from simple_module_hosting.bootstrap_settings import BootstrapSettings
from simple_module_hosting.setup_gate import STEP_MIGRATIONS, _database_migrated
from simple_module_hosting.setup_wizard.migrate import apply_migrations
from sqlalchemy.ext.asyncio import create_async_engine
from users.accounts.manager import UserManager
from users.core.token_secrets import resolve_token_secrets
from users.models import User
from users.module import UsersModule


@pytest.mark.parametrize("explicit_root", [False, True])
async def test_setup_tokens_survive_restart_and_workers_converge(
    tmp_path, monkeypatch, explicit_root
):
    for env in (
        "SM_SECRET_KEY",
        "SM_USERS_RESET_PASSWORD_TOKEN_SECRET",
        "SM_USERS_VERIFICATION_TOKEN_SECRET",
    ):
        monkeypatch.delenv(env, raising=False)
    if explicit_root:
        monkeypatch.setenv("SM_SECRET_KEY", "explicit-root")
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    database = tmp_path / "fresh.db"
    url = f"sqlite+aiosqlite:///{database}"
    (tmp_path / "versions").mkdir()
    (tmp_path / "versions/initial.py").write_text("revision = 'initial'\ndown_revision = None\n")
    (tmp_path / "alembic.ini").write_text("[alembic]\nscript_location = %(here)s\n")

    def upgrade(config, target):
        assert target == "heads"
        with closing(sqlite3.connect(database)) as db, db:
            db.execute(
                "CREATE TABLE settings_setting (id INTEGER PRIMARY KEY, scope TEXT NOT NULL, "
                "scope_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, "
                "value_type TEXT NOT NULL, UNIQUE (scope, scope_id, key))"
            )
            db.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
            db.execute("INSERT INTO alembic_version VALUES ('initial')")

    monkeypatch.setattr(command, "upgrade", upgrade)

    def build():
        settings = merge_host_settings(
            BootstrapSettings(
                _env_file=None,
                database_url=url,
                environment="testing",
            )
        )
        app = build_fastapi_app(settings, lifespan=None)
        AuthModule().register_settings(app)
        UsersModule().register_settings(app)
        registry = SetupRegistry()
        registry.add(
            SetupStep(
                id=STEP_MIGRATIONS,
                title="Migrations",
                is_complete=AsyncMock(return_value=False),
            )
        )
        app.state.sm = SimpleNamespace(
            settings=settings,
            db=SimpleNamespace(engine=create_async_engine(url)),
            setup_registry=registry,
        )
        app.state.deferred_startup = []
        app.state.migration = {"is_current": False, "current_revision": None}
        return app

    first, peer = build(), build()
    apps = [first, peer]
    before = first.state.sm.settings.secret_key
    # Keep a manager alive across migration to catch init-time key snapshots.
    manager = UserManager(None, None, first.state.users.settings, first.state.users.token_secrets)
    try:
        result = await apply_migrations(SimpleNamespace(app=first, state=SimpleNamespace()), {})
        assert result["migration"]["is_current"]
        assert await _database_migrated(peer)
        root = first.state.sm.settings.secret_key
        assert peer.state.sm.settings.secret_key == root
        with closing(sqlite3.connect(database)) as db:
            stored = db.execute(
                "SELECT value FROM settings_setting WHERE key = 'host.secret_key'"
            ).fetchone()
        if explicit_root:
            assert root == before == "explicit-root"
            assert stored is None
        else:
            assert root != before
            assert stored == (root,)
        expected = resolve_token_secrets(root)
        assert manager.reset_password_token_secret == expected.reset_password_token_secret
        assert manager.verification_token_secret == expected.verification_token_secret
        user = User(id=uuid.uuid4(), email="owner@example.com", hashed_password="unused")
        token = manager.mint_invite_token(user)
        restarted = build()
        apps.append(restarted)
        assert decode_jwt(
            token,
            restarted.state.users.token_secrets.verification_token_secret,
            [manager.verification_token_audience],
        )["sub"] == str(user.id)
    finally:
        for app in apps:
            await app.state.sm.db.engine.dispose()
