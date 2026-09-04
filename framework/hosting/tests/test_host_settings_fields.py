"""The nine boot knobs that moved from env-only to DB-backed.

Each of these was previously reachable only by editing ``.env`` and
redeploying. They are declared on ``HostSettings`` now, which means the
pre-app read picks them up, so the combined ``Settings`` must still expose
them unchanged — every consumer reads ``settings.<field>`` and does not care
which base class declares it.
"""

from __future__ import annotations

import pytest
from simple_module_hosting.bootstrap_settings import BootstrapSettings
from simple_module_hosting.host_settings import HostSettings
from simple_module_hosting.settings import Settings

MOVED_FIELDS = (
    "trusted_proxy",
    "log_level",
    "log_format",
    "auth_provider",
    "auth_public_paths",
    "db_pool_size",
    "db_max_overflow",
    "db_pool_pre_ping",
    "db_pool_recycle",
)

POOL_FIELDS = ("db_pool_size", "db_max_overflow", "db_pool_pre_ping", "db_pool_recycle")


@pytest.mark.parametrize("field", MOVED_FIELDS)
def test_field_is_db_backed(field: str) -> None:
    assert field in HostSettings.model_fields


@pytest.mark.parametrize("field", MOVED_FIELDS)
def test_field_no_longer_env_only(field: str) -> None:
    """Left on BootstrapSettings it would keep shadowing the DB value."""
    assert field not in BootstrapSettings.model_fields


@pytest.mark.parametrize("field", MOVED_FIELDS)
def test_combined_settings_still_exposes(field: str) -> None:
    assert field in Settings.model_fields


@pytest.mark.parametrize("field", POOL_FIELDS)
def test_pool_fields_marked_requires_restart(field: str) -> None:
    """The engine is built once at boot, so the admin UI must say a change
    here needs a restart rather than appearing to take effect live."""
    extra = HostSettings.model_fields[field].json_schema_extra
    assert extra is not None, f"{field} has no json_schema_extra"
    assert extra.get("requires_restart") is True


def test_database_url_stays_env_only() -> None:
    """The one value that cannot come from the DB, because it opens the DB."""
    assert "database_url" in BootstrapSettings.model_fields
    assert "database_url" not in HostSettings.model_fields


def test_trusted_proxy_normalizes_blank() -> None:
    """A stray space would otherwise be parsed by uvicorn as a literal host
    that matches no client, so request logs and the audit trail would keep
    attributing every request to the proxy instead of the real visitor."""
    assert HostSettings(trusted_proxy="  ").trusted_proxy is None
    assert HostSettings(trusted_proxy="*").trusted_proxy == "*"


def test_auth_provider_blank_falls_back() -> None:
    """``SM_AUTH_PROVIDER=`` yields '', which matches no installed provider
    and would otherwise mount all of them."""
    assert HostSettings(auth_provider="  ").auth_provider == "users"


def test_defaults_unchanged() -> None:
    """Moving a field must not quietly change what a fresh install gets."""
    s = HostSettings()
    assert s.log_level == "INFO"
    assert s.log_format == "json"
    assert s.db_pool_size == 10
    assert s.db_max_overflow == 20
    assert s.db_pool_pre_ping is True
    assert s.db_pool_recycle == 1800
    assert s.trusted_proxy is None
    assert s.auth_public_paths == []


def test_merge_host_settings_is_exported() -> None:
    """host/main.py builds its own Settings and passes it to create_app, so
    create_app's `settings or merge_host_settings()` fallback never fires in
    the real host. main.py has to call this itself."""
    from simple_module_hosting import merge_host_settings

    assert callable(merge_host_settings)
