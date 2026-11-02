"""The pre-app host-settings read: quiet on a fresh install, loud on a failure.

``multi_tenant`` is consumed while ``create_app`` builds the middleware stack,
so a worker that boots while the database is briefly unreachable and falls
back to defaults serves requests single-tenant — no tenant middleware, no
strict filter — next to siblings that stayed isolated (#494). A missing table
is the opposite case: an ordinary fresh install that must boot to show the
setup wizard.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from _hosting_settings_db import connection_refused as _refused
from _hosting_settings_db import unmigrated_db_url as _unmigrated
from simple_module_hosting import _preapp_config
from simple_module_hosting._preapp_config import (
    HostSettingsUnavailableError,
    load_host_overrides,
    merge_host_settings,
)
from simple_module_hosting.bootstrap_settings import BootstrapSettings

_LOGGER = "simple_module_hosting._preapp_config"
_SECRET = "a-test-secret-that-is-not-the-placeholder-0000000000"


def _bootstrap(url: str, environment: str) -> BootstrapSettings:
    return BootstrapSettings(
        _env_file=None, database_url=url, environment=environment, secret_key=_SECRET
    )


@pytest.mark.parametrize("environment", ["development", "production"])
def test_missing_table_is_quiet_in_every_environment(
    tmp_path: Path, environment: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A fresh install must boot (to show the wizard) without crying wolf."""
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        merged = merge_host_settings(_bootstrap(_unmigrated(tmp_path), environment))

    assert merged.multi_tenant is False
    assert not [r for r in caplog.records if r.name == _LOGGER and r.levelno >= logging.WARNING]


def test_strict_read_of_missing_table_returns_empty(tmp_path: Path) -> None:
    assert load_host_overrides(_unmigrated(tmp_path), strict=True) == {}


def test_connection_failure_warns_in_development(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    monkeypatch.setattr(_preapp_config, "_read", _refused)

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        merged = merge_host_settings(_bootstrap(_unmigrated(tmp_path), "development"))

    assert merged.multi_tenant is False
    warnings = [r for r in caplog.records if r.name == _LOGGER and r.levelno == logging.WARNING]
    assert warnings and "OSError" in warnings[0].getMessage()


def test_connection_failure_refuses_boot_outside_development(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Building with defaults would silently turn multi_tenant off on this worker."""
    monkeypatch.setattr(_preapp_config, "_read", _refused)

    with pytest.raises(HostSettingsUnavailableError, match="multi_tenant"):
        merge_host_settings(_bootstrap(_unmigrated(tmp_path), "production"))


def test_unreachable_postgres_refuses_boot_outside_development() -> None:
    """The real failure, not a patched one: nothing listens on port 1."""
    url = "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/nothing"
    with pytest.raises(HostSettingsUnavailableError):
        merge_host_settings(_bootstrap(url, "production"))
