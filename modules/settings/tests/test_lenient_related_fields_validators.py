"""Every cross-field settings validator declares RELATED_FIELDS_CTX (#558).

Seed a stored value that violates the rule and check lenient hydration drops
only the stored culprit, keeping the module's other overrides.
"""

from __future__ import annotations

import pytest
from background_tasks.settings import ENV_PREFIX, BackgroundTasksSettings
from file_storage.settings import FileStorageSettings
from keycloak.settings import KeycloakSettings
from pydantic import ValidationError
from simple_module_core.settings_hydrate import RELATED_FIELDS_CTX, build_settings
from simple_module_core.stored_settings import construct_leniently
from simple_module_hosting.host_settings import HostSettings
from site_lock.settings import SiteLockSettings
from users.settings import UsersSettings


def _int(v: int) -> tuple[str, str]:
    return (str(v), "int")


def _str(v: str) -> tuple[str, str]:
    return (v, "string")


def _bool(v: bool) -> tuple[str, str]:
    return (str(v).lower(), "bool")


def test_bg_handler_timeout_over_lease_drops_only_the_timeout() -> None:
    stored = {
        "outbox_lease_seconds": _int(100),
        "outbox_handler_timeout_seconds": _int(500),
        "max_retries": _int(7),
    }
    cfg = build_settings(BackgroundTasksSettings, stored, lenient=True)
    assert cfg.outbox_handler_timeout_seconds is None
    assert (cfg.outbox_lease_seconds, cfg.max_retries) == (100, 7)


def test_bg_handler_timeout_pinned_by_env_drops_the_stored_lease(monkeypatch) -> None:
    monkeypatch.setenv(f"{ENV_PREFIX}OUTBOX_HANDLER_TIMEOUT_SECONDS", "200")
    stored = {"outbox_lease_seconds": _int(100), "max_retries": _int(7)}
    cfg = build_settings(BackgroundTasksSettings, stored, lenient=True)
    assert cfg.outbox_handler_timeout_seconds == 200
    assert cfg.max_retries == 7
    assert cfg.outbox_lease_seconds != 100


def test_file_storage_s3_missing_config_drops_the_stored_backend() -> None:
    stored = {
        "backend": _str("s3"),
        "s3_bucket": _str("b"),
        "max_file_size_bytes": _int(1234),
    }
    cfg = build_settings(FileStorageSettings, stored, lenient=True)
    assert cfg.backend != "s3"
    assert cfg.max_file_size_bytes == 1234


def test_file_storage_error_is_located_and_message_unchanged() -> None:
    with pytest.raises(ValidationError) as exc:
        FileStorageSettings(backend="s3", s3_bucket="b")
    err = exc.value.errors()[0]
    assert err["loc"] == ("s3_region",)
    assert "S3 backend selected but s3_region is not set." in err["msg"]
    assert "backend" in err["ctx"][RELATED_FIELDS_CTX]


def test_site_lock_enabled_without_password_drops_only_enabled() -> None:
    stored = {"enabled": _bool(True), "password": _str(""), "message": _str("maintenance")}
    cfg = build_settings(SiteLockSettings, stored, lenient=True)
    assert cfg.enabled is False
    assert cfg.message == "maintenance"


def test_host_default_locale_unsupported_drops_only_the_stored_locale() -> None:
    cfg = construct_leniently(
        HostSettings,
        {"i18n_default_locale": "zz", "maintenance_message": "Keep me"},
    )
    assert cfg.i18n_default_locale in cfg.i18n_supported_locales
    assert cfg.maintenance_message == "Keep me"


def test_users_placeholder_secret_in_production_is_located_and_still_refused(monkeypatch) -> None:
    monkeypatch.setenv("SM_ENVIRONMENT", "production")
    stored = {"reset_password_token_lifetime_seconds": _int(99)}
    with pytest.raises(ValidationError) as exc:
        build_settings(UsersSettings, stored, lenient=True)
    err = exc.value.errors()[0]
    assert err["loc"] == ("reset_password_token_secret",)
    assert set(err["ctx"][RELATED_FIELDS_CTX]) == {
        "reset_password_token_secret",
        "verification_token_secret",
    }


def test_keycloak_missing_config_in_production_is_located_and_still_refused(monkeypatch) -> None:
    monkeypatch.setenv("SM_ENVIRONMENT", "production")
    stored = {"realm": _str("r"), "client_id": _str("c")}
    with pytest.raises(ValidationError) as exc:
        build_settings(KeycloakSettings, stored, lenient=True)
    err = exc.value.errors()[0]
    assert err["loc"] == ("server_url",)
    assert "SM_KEYCLOAK_SERVER_URL" in err["msg"]
    assert "realm" in err["ctx"][RELATED_FIELDS_CTX]
