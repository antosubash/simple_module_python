"""Compatibility errors gate established hosts before settings or startup (#711)."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_hosting._lifespan import build_lifespan
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.parametrize(
    ("environment", "severity", "never_migrated", "refuses"),
    [
        ("production", "error", False, True),
        ("testing", "error", False, True),
        ("development", "error", False, False),
        ("production", "warning", False, False),
        ("production", "error", True, False),
    ],
)
async def test_hosting_compatibility_before_hydration(
    monkeypatch, environment, severity, never_migrated, refuses
):
    from simple_module_core.data_compatibility import DataCompatibilityIssue

    events = []

    class Module(ModuleBase):
        meta = ModuleMeta(name="Example")

        async def check_data_compatibility(self, db):
            events.append("check")
            return [
                DataCompatibilityIssue(
                    upgrade_id="example.v1", message="Upgrade", severity=severity
                )
            ]

        async def on_startup(self, app):
            events.append("startup")

    async def status(engine):
        return {"is_current": True, "current_revision": None if never_migrated else "local"}

    async def hydrate(app):
        events.append("hydrate")

    monkeypatch.setattr("simple_module_hosting._lifespan.migration_status", status)
    monkeypatch.setattr("simple_module_hosting._lifespan.hydrate_settings_from_db", hydrate)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    app = FastAPI()
    app.state.sm = SimpleNamespace(
        db=SimpleNamespace(engine=engine, session_factory=async_sessionmaker(engine)),
        settings=SimpleNamespace(environment=environment),
    )
    if refuses:
        with pytest.raises(RuntimeError, match=r"example\.v1"):
            async with build_lifespan([Module()])(app):
                pass
        assert events == ["check"]
    else:
        async with build_lifespan([Module()])(app):
            assert events == (
                ["hydrate", "startup"] if never_migrated else ["check", "hydrate", "startup"]
            )


async def test_partly_migrated_first_run_defers_the_check(monkeypatch):
    # A first run that stopped part-way has a revision but pre-upgrade columns:
    # judging it would refuse the boot and hide the wizard that finishes it.
    events = []

    class Module(ModuleBase):
        meta = ModuleMeta(name="Example")

        async def check_data_compatibility(self, db):
            events.append("check")
            return []

    async def status(engine):
        return {"is_current": False, "current_revision": "partial", "pending_count": 3}

    async def first_run(app):
        return True

    async def hydrate(app):
        events.append("hydrate")

    monkeypatch.setattr("simple_module_hosting._lifespan.migration_status", status)
    monkeypatch.setattr("simple_module_hosting._lifespan._is_first_run", first_run)
    monkeypatch.setattr("simple_module_hosting._lifespan.hydrate_settings_from_db", hydrate)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    app = FastAPI()
    app.state.sm = SimpleNamespace(
        db=SimpleNamespace(engine=engine, session_factory=async_sessionmaker(engine)),
        settings=SimpleNamespace(environment="production"),
    )
    async with build_lifespan([Module()])(app):
        assert "check" not in events
        assert app.state.deferred_data_compatibility


async def test_hosting_deferred_checks_gate_replay_before_hydration(monkeypatch):
    from simple_module_core.data_compatibility import DataCompatibilityIssue
    from simple_module_hosting._deferred_startup import run_deferred_startup

    class Module(ModuleBase):
        meta = ModuleMeta(name="Example")

        async def check_data_compatibility(self, db):
            return [
                DataCompatibilityIssue(upgrade_id="example.v1", message="Upgrade", severity="error")
            ]

    app = FastAPI()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    app.state.sm = SimpleNamespace(
        db=SimpleNamespace(engine=engine, session_factory=async_sessionmaker(engine)),
        settings=SimpleNamespace(environment="production"),
    )
    app.state.deferred_data_compatibility = [Module()]
    app.state.deferred_startup = []
    try:
        with pytest.raises(RuntimeError, match=r"example\.v1"):
            await run_deferred_startup(app)
        assert app.state.deferred_data_compatibility
    finally:
        await engine.dispose()


@pytest.mark.parametrize("check_raises", [False, True])
async def test_hosting_setup_gate_keeps_incompatible_replay_closed(monkeypatch, check_raises):
    from simple_module_core.data_compatibility import DataCompatibilityIssue
    from simple_module_hosting.setup_gate import _database_migrated

    class Module(ModuleBase):
        meta = ModuleMeta(name="Example")

        async def check_data_compatibility(self, db):
            if check_raises:
                raise RuntimeError("database unavailable")
            return [
                DataCompatibilityIssue(upgrade_id="example.v1", message="Upgrade", severity="error")
            ]

    app = FastAPI()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    app.state.sm = SimpleNamespace(
        db=SimpleNamespace(engine=engine, session_factory=async_sessionmaker(engine)),
        settings=SimpleNamespace(environment="production"),
    )
    app.state.migration = {"is_current": False, "current_revision": None}
    app.state.deferred_data_compatibility = [Module()]
    app.state.deferred_startup = []

    async def status(engine):
        return {"is_current": True, "current_revision": "local"}

    monkeypatch.setattr("simple_module_hosting.setup_gate.migrations.migration_status", status)
    try:
        assert await _database_migrated(app) is False
        assert await _database_migrated(app) is False
    finally:
        await engine.dispose()
