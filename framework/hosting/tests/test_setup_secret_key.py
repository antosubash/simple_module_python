"""A first-run root must converge before deferred modules issue any tokens."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from simple_module_hosting import _secret_key
from simple_module_hosting._deferred_startup import run_deferred_startup
from simple_module_hosting._preapp_config import merge_host_settings
from simple_module_hosting.bootstrap_settings import BootstrapSettings
from simple_module_hosting.setup_gate import _database_migrated


@pytest.mark.parametrize("explicit", [False, True])
async def test_deferred_startup_resolves_only_ephemeral_roots(monkeypatch, explicit):
    monkeypatch.delenv("SM_SECRET_KEY", raising=False)
    monkeypatch.setattr(
        "simple_module_hosting._preapp_config.load_host_overrides", lambda *a, **k: {}
    )
    ensure = AsyncMock(return_value=None)
    monkeypatch.setattr(_secret_key, "_ensure", ensure)
    values = {"secret_key": "explicit-root"} if explicit else {}
    settings = merge_host_settings(
        BootstrapSettings(_env_file=None, environment="testing", **values)
    )
    first_root = settings.secret_key
    app = SimpleNamespace(
        state=SimpleNamespace(
            boot_settings=settings,
            sm=SimpleNamespace(settings=settings),
            deferred_startup=[],
            migration={"is_current": True},
        )
    )
    ensure.return_value = "stored-root"
    await run_deferred_startup(app)
    assert settings.secret_key == (first_root if explicit else "stored-root")
    assert app.state.sm.settings.secret_key == settings.secret_key
    assert not settings._secret_key_ephemeral


async def test_failed_persistence_keeps_setup_closed(monkeypatch):
    from simple_module_hosting.settings import Settings

    settings = Settings(_env_file=None, environment="testing", secret_key="ephemeral-root")
    settings._secret_key_ephemeral = True
    app = SimpleNamespace(
        state=SimpleNamespace(
            boot_settings=settings,
            sm=SimpleNamespace(settings=settings),
            deferred_startup=[],
        )
    )
    monkeypatch.delenv("SM_SECRET_KEY", raising=False)
    ensure = AsyncMock(side_effect=OSError("DB unavailable"))
    monkeypatch.setattr(_secret_key, "_ensure", ensure)
    with pytest.raises(_secret_key.SecretKeyUnavailableError):
        await run_deferred_startup(app)
    assert settings.secret_key == "ephemeral-root"
    assert settings._secret_key_ephemeral
    app.state.migration = {"is_current": True}
    assert not await _database_migrated(app)
    ensure.side_effect = None
    ensure.return_value = "stored-root"
    assert await _database_migrated(app)
    assert settings.secret_key == "stored-root"
