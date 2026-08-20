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


def test_env_file_none_anchors_sqlite_at_project_root_not_cwd(tmp_path, monkeypatch):
    """`_env_file=None` is pydantic-settings' documented idiom for "load no
    .env file at all" — but relative sqlite paths must still anchor at the
    project root discovered by find_env_file(), not the process cwd, or a
    CLI run from a subdirectory (e.g. host/) would create app.db there
    instead of at the project root.
    """
    project_root = tmp_path
    (project_root / ".git").mkdir()
    workdir = project_root / "host"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    monkeypatch.delenv("SM_PROJECT_ROOT", raising=False)
    monkeypatch.setenv("SM_DATABASE_URL", "sqlite+aiosqlite:///./app.db")
    monkeypatch.setenv("SM_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("SM_ENVIRONMENT", "development")

    bs = BootstrapSettings(_env_file=None)

    expected = (project_root / "app.db").resolve()
    assert bs.database_url == f"sqlite+aiosqlite:///{expected}"


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


@pytest.mark.asyncio
async def test_host_settings_registered_as_host_package(app):
    registry = app.state.settings.module_registry
    assert registry.get("host").__name__ == "HostSettings"
    assert isinstance(
        app.state.host.settings,
        __import__("simple_module_hosting.host_settings", fromlist=["HostSettings"]).HostSettings,
    )
