"""Injected databases are wired normally and remain caller-owned (#967)."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from simple_module_db import init_db
from simple_module_db.engine.deps import get_db
from simple_module_hosting.boot import _app_boot, _lifespan, app_builder
from sqlalchemy.engine import make_url


@pytest.fixture
def database_app(settings, monkeypatch):
    settings = settings.model_copy(update={"multi_tenant": False})
    monkeypatch.setattr(app_builder, "discover_modules", lambda **kwargs: [])
    monkeypatch.setattr(_lifespan, "migration_status", AsyncMock(return_value={"is_current": True}))
    monkeypatch.setattr(_lifespan, "hydrate_settings_from_db", AsyncMock())
    return settings


@pytest.mark.parametrize("factory", [False, True], ids=["state", "factory"])
@pytest.mark.parametrize("startup_fails", [False, True], ids=["shutdown", "startup-failure"])
async def test_supplied_database_is_used_and_not_disposed(
    database_app, monkeypatch, factory, startup_fails
):
    state = init_db("sqlite+aiosqlite:///:memory:")
    pool = state.engine.pool
    received = []

    def make_database(settings):
        received.append(settings)
        return state

    def unexpected_engine(*args, **kwargs):
        pytest.fail("create_app constructed a second database")

    monkeypatch.setattr(_app_boot, "init_db", unexpected_engine)
    try:
        app = app_builder.create_app(database_app, database=make_database if factory else state)
        assert app.state.sm.db is state
        assert received == ([database_app] if factory else [])
        assert state._listeners_registered
        assert not state.tenant_strict
        async with asynccontextmanager(get_db)(Request({"type": "http", "app": app})) as session:
            assert session.bind is state.engine
        if startup_fails:
            monkeypatch.setattr(
                _lifespan, "migration_status", AsyncMock(side_effect=RuntimeError("startup"))
            )
            with pytest.raises(RuntimeError, match="startup"):
                async with app.router.lifespan_context(app):
                    pytest.fail("startup should have failed")
        else:
            async with app.router.lifespan_context(app):
                assert app.state.sm.db is state
        # AsyncEngine.dispose replaces the pool even when it has no connections.
        assert state.engine.pool is pool
    finally:
        await state.engine.dispose()


@pytest.mark.parametrize(
    "database_url", [None, "postgresql+asyncpg://user:test-password@localhost/test_db"]
)
async def test_default_database_is_created_and_disposed(database_app, database_url):
    if database_url is not None:
        database_app = database_app.model_copy(update={"database_url": database_url})
    app = app_builder.create_app(database_app)
    state = app.state.sm.db
    assert state.engine.url == make_url(database_app.database_url)
    assert state._listeners_registered
    pool = state.engine.pool
    async with app.router.lifespan_context(app):
        assert app.state.sm.db is state
    assert state.engine.pool is not pool


async def test_host_builder_passes_database_factory(database_app, isolated_host_root, monkeypatch):
    import sys

    from simple_module_hosting.boot.host import build_host_app

    state = init_db("sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.chdir(isolated_host_root)
    monkeypatch.setenv("SM_PROJECT_ROOT", str(isolated_host_root))
    monkeypatch.setattr("simple_module_hosting.merge_host_settings", lambda: database_app)
    monkeypatch.setattr(
        "simple_module_hosting.observability.logging.setup_logging", lambda **kwargs: None
    )
    try:
        app = build_host_app(isolated_host_root / "main.py", database=lambda settings: state)
        assert app.state.sm.db is state
    finally:
        await state.engine.dispose()
