from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from pydantic_settings import BaseSettings
from settings.contracts.events import SettingsReloaded
from settings.registration import register_module_settings
from settings.reload import apply_changes_and_reload
from settings.service import SettingService
from settings.services import SettingsServices
from settings.settings import SettingsSettings
from settings.store import SettingsStore
from simple_module_core.events import EventBus


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
    assert app.state.users.settings is new_settings
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
