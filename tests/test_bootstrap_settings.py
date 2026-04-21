from __future__ import annotations

import pytest

from simple_module_hosting.bootstrap_settings import BootstrapSettings
from simple_module_hosting.host_settings import HostSettings


def test_bootstrap_reads_from_env(monkeypatch):
    monkeypatch.setenv("SM_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SM_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("SM_ENVIRONMENT", "development")
    bs = BootstrapSettings()
    assert bs.database_url == "sqlite+aiosqlite:///:memory:"
    assert bs.secret_key == "x" * 48
    assert bs.environment == "development"


def test_bootstrap_placeholder_secret_blocks_production(monkeypatch):
    monkeypatch.setenv("SM_ENVIRONMENT", "production")
    monkeypatch.setenv("SM_SECRET_KEY", "change-me-in-production")
    with pytest.raises(ValueError, match="SM_SECRET_KEY"):
        BootstrapSettings()


def test_host_settings_ignores_env(monkeypatch):
    # HostSettings must NOT read env — env-sprawl is what we're removing.
    monkeypatch.setenv("SM_MULTI_TENANT", "true")
    hs = HostSettings()
    assert hs.multi_tenant is False  # default wins; env ignored


def test_host_settings_default_locale_must_be_supported():
    with pytest.raises(ValueError):
        HostSettings(i18n_default_locale="de", i18n_supported_locales=["en"])
