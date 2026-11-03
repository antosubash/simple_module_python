"""Bootstrap and runtime settings use consistent sources (#783, #793)."""

import os
from pathlib import Path

import pytest
from simple_module_core.settings_hydrate import build_settings, env_supplied_fields
from simple_module_hosting._preapp_config import merge_host_settings
from simple_module_hosting.bootstrap_settings import BootstrapSettings
from simple_module_hosting.host_settings import HostSettings


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for key in os.environ:
        if key.startswith("SM_"):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    return tmp_path


def test_explicit_bootstrap_fields_survive_merge(project: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "simple_module_hosting._preapp_config.load_host_overrides", lambda *a, **k: {}
    )
    bootstrap = BootstrapSettings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{project}/bootstrap.db",
        secret_key="k" * 64,
        environment="production",
        modules_enabled=["Users"],
        redis_url="redis://example.org/1",
        debug=True,
        vite_dev_url="http://localhost:5999",
    )
    merged = merge_host_settings(bootstrap, strict=False)
    for name in BootstrapSettings.model_fields:
        assert getattr(merged, name) == getattr(bootstrap, name), name


def test_unset_bootstrap_fields_still_read_env(project: Path, monkeypatch) -> None:
    url = f"sqlite+aiosqlite:///{project}/settings.db"
    monkeypatch.setattr(
        "simple_module_hosting._preapp_config.load_host_overrides",
        lambda *a, **k: {"log_level": ("WARNING", "string")},
    )
    bootstrap = BootstrapSettings(_env_file=None, database_url=url, secret_key="k" * 64)
    monkeypatch.setenv("SM_DEBUG", "true")
    monkeypatch.setenv("SM_LOG_LEVEL", "ERROR")
    merged = merge_host_settings(bootstrap)
    assert merged.debug is True
    assert merged.log_level == "ERROR"


@pytest.mark.parametrize("subdirectory", [False, True])
def test_dotenv_beats_db_at_boot_and_runtime(project: Path, monkeypatch, subdirectory) -> None:
    url = f"sqlite+aiosqlite:///{project}/settings.db"
    (project / ".env").write_text("SM_PUBLIC_BASE_URL=https://env.example\n")
    if subdirectory:
        child = project / "child"
        child.mkdir()
        monkeypatch.chdir(child)
    monkeypatch.setattr(
        "simple_module_hosting._preapp_config.load_host_overrides",
        lambda *a, **k: {"public_base_url": ("https://db.example", "string")},
    )
    boot = merge_host_settings(BootstrapSettings(database_url=url, secret_key="k" * 64))
    runtime = build_settings(HostSettings, {"public_base_url": ("https://db.example", "string")})
    assert boot.public_base_url == runtime.public_base_url == "https://env.example"
    assert "public_base_url" in env_supplied_fields(HostSettings)
    assert "SM_PUBLIC_BASE_URL" not in os.environ


def test_host_settings_explicit_env_file_and_opt_out(project: Path, monkeypatch) -> None:
    (project / ".env").write_text("SM_PUBLIC_BASE_URL=https://default.example\n")
    custom = project / "custom.env"
    custom.write_text("SM_PUBLIC_BASE_URL=https://custom.example\n")
    assert HostSettings(_env_file=custom).public_base_url == "https://custom.example"
    assert HostSettings(_env_file=None).public_base_url == ""
    child = project / "child"
    child.mkdir()
    monkeypatch.chdir(child)
    assert HostSettings(_env_file=".env").public_base_url == ""
    assert HostSettings().public_base_url == "https://default.example"
