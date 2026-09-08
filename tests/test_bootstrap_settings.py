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


def test_host_settings_reads_its_own_prefixed_env(monkeypatch):
    """Env beats the default. This test asserted the opposite and never ran.

    ``testpaths`` did not list ``tests/``, so nothing here was collected by a
    bare ``pytest`` — the stale assertion sat green for as long as it took to
    notice. The contract it claimed ("HostSettings must NOT read env") is not
    the one the codebase has: precedence is env → DB → default, and env has to
    keep winning or an upgrade silently changes a deployment's behaviour
    (CLAUDE.md § Conventions). ``HostSettings`` declares ``env_prefix="SM_"``
    for exactly that reason.
    """
    monkeypatch.setenv("SM_MULTI_TENANT", "true")
    assert HostSettings().multi_tenant is True


def test_host_settings_ignores_unprefixed_env(monkeypatch):
    """What the ``env_prefix`` is actually defending against.

    Without it a bare ``HostSettings()`` would read unprefixed names, and
    ``LOG_LEVEL`` in particular is a common variable that has nothing to do
    with this app.
    """
    monkeypatch.delenv("SM_MULTI_TENANT", raising=False)
    monkeypatch.setenv("MULTI_TENANT", "true")
    assert HostSettings().multi_tenant is False


def test_host_settings_default_wins_when_env_is_unset(monkeypatch):
    monkeypatch.delenv("SM_MULTI_TENANT", raising=False)
    assert HostSettings().multi_tenant is False


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
