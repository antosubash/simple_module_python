from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from pydantic_settings import BaseSettings
from settings.contracts.events import SettingsReloaded
from settings.core.service import SettingService
from settings.core.services import SettingsServices
from settings.core.settings import SettingsSettings
from settings.module_settings.reload import apply_changes_and_reload, clear_override_and_reload
from settings.module_settings.store import SettingsStore
from simple_module_core.events import EventBus
from simple_module_core.module_settings import register_module_settings
from simple_module_db.transaction import finalize_session


class _UsersCfg(BaseSettings):
    allow_signup: bool = False
    smtp_port: int = 25


@dataclass
class _UsersServices:
    settings: _UsersCfg


@pytest.fixture
def app_and_bus(db_session) -> tuple[FastAPI, EventBus]:
    bus = EventBus()
    app = FastAPI()
    app.state.settings = SettingsServices(settings=SettingsSettings())
    register_module_settings(app, "users", _UsersCfg, lambda s: _UsersServices(settings=s))
    return app, bus


@pytest.mark.asyncio
async def test_apply_changes_updates_app_state_and_fires_event(app_and_bus, db_session):
    app, bus = app_and_bus
    received: list[SettingsReloaded] = []

    async def handler(evt: SettingsReloaded) -> None:
        received.append(evt)

    bus.subscribe(SettingsReloaded, handler)

    store = SettingsStore(SettingService(db_session))
    new_settings = await apply_changes_and_reload(
        app,
        bus,
        store,
        package="users",
        changes={"allow_signup": True, "smtp_port": 587},
    )

    assert new_settings.allow_signup is True
    assert new_settings.smtp_port == 587
    assert app.state.users.settings.allow_signup is False
    assert received == []
    await finalize_session(db_session)
    assert app.state.users.settings == new_settings
    assert received == [SettingsReloaded(package="users", changed=("allow_signup", "smtp_port"))]

    persisted = await store.get_overrides("users")
    assert persisted == {"allow_signup": ("True", "bool"), "smtp_port": ("587", "int")}


@pytest.mark.asyncio
async def test_apply_changes_validation_error_rolls_back(app_and_bus, db_session):
    app, bus = app_and_bus
    store = SettingsStore(SettingService(db_session))

    original = app.state.users.settings

    with pytest.raises(ValidationError):
        await apply_changes_and_reload(
            app,
            bus,
            store,
            package="users",
            changes={"smtp_port": "not-an-int"},
        )

    assert app.state.users.settings is original
    assert await store.get_overrides("users") == {}


@pytest.mark.asyncio
async def test_apply_changes_unknown_package_raises(app_and_bus, db_session):
    app, bus = app_and_bus
    store = SettingsStore(SettingService(db_session))

    with pytest.raises(KeyError):
        await apply_changes_and_reload(
            app,
            bus,
            store,
            package="unknown",
            changes={"x": 1},
        )


async def test_multiple_settings_edits_in_one_transaction_keep_both(app_and_bus, db_session):
    app, bus = app_and_bus
    store = SettingsStore(SettingService(db_session))
    await apply_changes_and_reload(app, bus, store, package="users", changes={"allow_signup": True})
    await apply_changes_and_reload(app, bus, store, package="users", changes={"smtp_port": 587})
    assert app.state.users.settings.allow_signup is False
    assert app.state.users.settings.smtp_port == 25
    await finalize_session(db_session)
    assert app.state.users.settings.allow_signup is True
    assert app.state.users.settings.smtp_port == 587


@pytest.mark.parametrize("operation", ["update", "reset"])
async def test_settings_write_locks_package_before_reading(
    app_and_bus, db_session, monkeypatch, operation
):
    app, bus = app_and_bus
    store = SettingsStore(SettingService(db_session))
    locked = []
    read = store.get_overrides

    async def lock(package):
        locked.append(package)

    async def read_after_lock(package):
        assert locked == ["users"]
        return await read(package)

    monkeypatch.setattr(store, "lock_package", lock, raising=False)
    monkeypatch.setattr(store, "get_overrides", read_after_lock)
    if operation == "update":
        await apply_changes_and_reload(app, bus, store, package="users", changes={"smtp_port": 587})
    else:
        await clear_override_and_reload(app, bus, store, package="users", field="smtp_port")
    assert locked == ["users"]
