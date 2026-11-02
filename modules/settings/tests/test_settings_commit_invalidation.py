"""Module settings and reload events only reflect committed state."""

import pytest
from settings.contracts.events import SettingsReloaded
from settings.reload import apply_changes_and_reload
from settings.service import SettingService
from settings.store import SettingsStore
from simple_module_core.invalidation import Invalidation
from simple_module_db.transaction import finalize_session, rollback_session


@pytest.mark.parametrize("commit", [False, True])
async def test_settings_and_events_wait_for_commit(app, commit):
    received = []
    bus = app.state.sm.event_bus

    async def record(event):
        received.append(event)

    bus.subscribe(SettingsReloaded, record)
    original = app.state.users.settings
    wanted = not original.allow_signup
    async with app.state.sm.db.session_factory() as db:
        await apply_changes_and_reload(
            app,
            bus,
            SettingsStore(SettingService(db)),
            package="users",
            changes={"allow_signup": wanted},
        )
        assert app.state.users.settings is original
        assert received == []
        if commit:
            await finalize_session(db)
        else:
            await rollback_session(db)
    assert app.state.users.settings.allow_signup is (wanted if commit else original.allow_signup)
    assert len(received) == int(commit)
    if commit:
        assert received[0].changed == ("allow_signup",)


async def test_remote_settings_changes_and_clears_reload_and_emit_event(app):
    received = []

    async def record(event):
        received.append(event)

    app.state.sm.event_bus.subscribe(SettingsReloaded, record)
    original = app.state.users.settings.allow_signup
    factory = app.state.sm.db.session_factory
    async with factory() as db:
        await SettingsStore(SettingService(db)).set_override(
            "users", "allow_signup", str(not original), "bool"
        )
        await db.commit()
    message = Invalidation(channel="settings.modules", key="users", origin="other")
    await app.state.sm.invalidation.deliver(message.to_wire())
    assert app.state.users.settings.allow_signup is not original
    assert received[-1].changed == ("allow_signup",)
    async with factory() as db:
        await SettingsStore(SettingService(db)).clear_override("users", "allow_signup")
        await db.commit()
    await app.state.sm.invalidation.deliver(message.to_wire())
    assert app.state.users.settings.allow_signup is original
    assert len(received) == 2


@pytest.mark.parametrize("commit", [False, True])
async def test_clearing_module_setting_waits_for_commit(app, commit):
    from settings.endpoints.module_api import clear_module_field
    from starlette.requests import Request

    original = app.state.users.settings.allow_signup
    factory = app.state.sm.db.session_factory
    async with factory() as db:
        await SettingsStore(SettingService(db)).set_override(
            "users", "allow_signup", str(not original), "bool"
        )
        await db.commit()
    await app.state.sm.invalidation.publish("settings.modules", key="users")
    received = []

    async def record(event):
        received.append(event)

    app.state.sm.event_bus.subscribe(SettingsReloaded, record)
    async with factory() as db:
        await clear_module_field(
            "users", "allow_signup", Request({"type": "http", "app": app}), SettingService(db)
        )
        assert app.state.users.settings.allow_signup is not original
        assert received == []
        if commit:
            await finalize_session(db)
        else:
            await rollback_session(db)
    assert app.state.users.settings.allow_signup is (original if commit else not original)
    assert len(received) == int(commit)
