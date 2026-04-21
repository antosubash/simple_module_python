from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_lifespan_hydrates_host_settings_from_db(app, db_session):
    """After lifespan starts, host settings reflect DB overrides, not defaults."""
    from settings.service import SettingService
    from settings.store import SettingsStore

    store = SettingsStore(SettingService(db_session))
    await store.set_override("host", "multi_tenant", "true", "bool")

    from simple_module_hosting._hydrate_step import hydrate_all

    await hydrate_all(app, store)

    assert app.state.host.settings.multi_tenant is True
