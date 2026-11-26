"""Host title precedence: environment, DB, app default, framework (#1225)."""

import pytest
from simple_module_core.settings.settings_hydrate import build_settings
from simple_module_hosting.config._preapp_config import merge_host_settings
from simple_module_hosting.config.bootstrap_settings import BootstrapSettings


@pytest.mark.parametrize(
    "code,db,env,expected",
    [
        (None, None, None, "SimpleModule"),
        ("Acme", None, None, "Acme"),
        ("Acme", "Database API", None, "Database API"),
        ("Acme", "SimpleModule", None, "SimpleModule"),
        ("Acme", "Database API", "Environment API", "Environment API"),
        ("Acme", None, "Environment API", "Environment API"),
    ],
)
def test_host_title_precedence(monkeypatch, code, db, env, expected):
    monkeypatch.delenv("SM_API_TITLE", raising=False)
    if env is not None:
        monkeypatch.setenv("SM_API_TITLE", env)
    overrides = {"api_title": (db, "string")} if db is not None else {}
    monkeypatch.setattr(
        "simple_module_hosting.config._preapp_config.load_host_overrides",
        lambda *args, **kwargs: overrides,
    )
    bootstrap = BootstrapSettings(
        _env_file=None, database_url="sqlite+aiosqlite:///:memory:", secret_key="k" * 64
    )
    merged = merge_host_settings(bootstrap, app_name=code)
    assert merged.api_title == expected
    assert build_settings(type(merged), overrides).api_title == expected
