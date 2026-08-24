"""Key-prefix normalisation and S3 provider-compatibility client construction.

These are pure unit tests — no moto server — covering the settings validators
and the kwargs handed to aioboto3. The end-to-end prefixed round-trip lives in
``test_s3_backend.py`` where the moto fixtures are.
"""

from __future__ import annotations

import pytest
from file_storage import constants
from file_storage.backends.s3 import _build, _build_botocore_config
from file_storage.service import _generate_key
from file_storage.settings import FileStorageSettings
from pydantic import ValidationError

_BUCKET = "test-bucket"


def _s3_settings(**overrides) -> FileStorageSettings:
    base = {
        "backend": constants.BackendId.S3,
        "s3_bucket": _BUCKET,
        "s3_access_key_id": "test",
        "s3_secret_access_key": "test",
    }
    return FileStorageSettings(**{**base, **overrides})


# ── key_prefix normalisation ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("   ", ""),
        ("/", ""),
        ("media", "media/"),
        ("media/", "media/"),
        ("/media", "media/"),
        ("/media/", "media/"),
        ("a//b", "a/b/"),
        ("a/b/c", "a/b/c/"),
        ("./media", "media/"),
        ("uploads\\media", "uploads/media/"),
    ],
)
def test_key_prefix_normalises_to_canonical_form(raw: str, expected: str):
    assert FileStorageSettings(key_prefix=raw).key_prefix == expected


@pytest.mark.parametrize("raw", ["..", "../escape", "a/../b", "media/..", "C:/media"])
def test_key_prefix_rejects_traversal_and_absolute_paths(raw: str):
    """Rejected at config time — the filesystem backend's own guard would only
    surface this as a generic error at first upload."""
    with pytest.raises(ValidationError):
        FileStorageSettings(key_prefix=raw)


def test_key_prefix_defaults_to_bucket_root():
    assert FileStorageSettings().key_prefix == ""


# ── key generation ───────────────────────────────────────────────────


def test_generate_key_without_prefix_keeps_legacy_layout():
    key = _generate_key("photo.png")
    assert not key.startswith("/")
    assert key.endswith(".png")
    assert key.count("/") == 3  # YYYY/MM/DD/<uuid>.png


def test_generate_key_bakes_prefix_into_the_key():
    key = _generate_key("photo.png", "media/")
    assert key.startswith("media/")
    assert key.endswith(".png")


def test_generate_key_supports_nested_prefix():
    assert _generate_key("a.txt", "tenant/uploads/").startswith("tenant/uploads/")


# ── S3 provider compatibility ────────────────────────────────────────


def test_addressing_style_defaults_to_auto_and_builds_no_config():
    """All-default config must stay ``None`` so botocore keeps negotiating."""
    assert _build_botocore_config(_s3_settings()) is None


def test_path_addressing_reaches_botocore_config():
    config = _build_botocore_config(_s3_settings(s3_addressing_style="path"))
    assert config is not None
    assert config.s3["addressing_style"] == "path"


def test_signature_version_reaches_botocore_config():
    config = _build_botocore_config(_s3_settings(s3_signature_version="s3v4"))
    assert config is not None
    assert config.signature_version == "s3v4"


@pytest.mark.parametrize("raw", ["PATH", " path "])
def test_addressing_style_accepts_untidy_operator_input(raw: str):
    assert _s3_settings(s3_addressing_style=raw).s3_addressing_style == "path"


def test_addressing_style_rejects_unknown_value():
    with pytest.raises(ValidationError):
        _s3_settings(s3_addressing_style="bucket-hostname")


def test_s3_builds_without_an_explicit_region():
    """R2 and other region-less providers must boot; region is filler for SigV4."""
    backend = _build(_s3_settings(s3_region=""))
    assert backend.region == constants.DEFAULT_S3_REGION
    assert backend.client_kwargs["region_name"] == constants.DEFAULT_S3_REGION


def test_s3_backend_requires_only_a_bucket():
    with pytest.raises(ValidationError):
        _s3_settings(s3_bucket="")


def test_presign_uses_the_same_endpoint_when_no_public_one_is_set():
    backend = _build(_s3_settings(s3_endpoint_url="http://minio:9000"))
    assert backend.presign_client_kwargs["endpoint_url"] == "http://minio:9000"


def test_presign_uses_the_public_endpoint_when_configured():
    """The app talks to MinIO internally; browsers must get a reachable host."""
    backend = _build(
        _s3_settings(
            s3_endpoint_url="http://minio:9000",
            s3_public_endpoint_url="https://files.example.com",
        )
    )
    assert backend.client_kwargs["endpoint_url"] == "http://minio:9000"
    assert backend.presign_client_kwargs["endpoint_url"] == "https://files.example.com"
    # Credentials and config must carry across to the presigning client, or the
    # signature would be computed with different material than the request.
    assert backend.presign_client_kwargs["aws_access_key_id"] == "test"


def test_verify_ssl_disabled_reaches_client_kwargs():
    assert _build(_s3_settings(s3_verify_ssl=False)).client_kwargs["verify"] is False


def test_verify_ssl_enabled_leaves_kwargs_untouched():
    assert "verify" not in _build(_s3_settings()).client_kwargs


# ── live reconfiguration ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_settings_reload_rebuilds_the_backend(app):
    """Editing storage config in the admin UI must take effect without a restart.

    The backend is built once at startup, so without the SettingsReloaded
    subscription the settings would save while uploads kept using the old
    provider — the change would appear to apply and silently do nothing.
    """
    from settings.contracts.events import SettingsReloaded

    state = app.state.file_storage
    original = state.backend
    assert original.backend_id == constants.BackendId.FILESYSTEM

    state.settings = state.settings.model_copy(
        update={
            "backend": constants.BackendId.S3,
            "s3_bucket": _BUCKET,
            "s3_access_key_id": "test",
            "s3_secret_access_key": "test",
        }
    )
    await app.state.sm.event_bus.publish(
        SettingsReloaded(package="file_storage", changed=("backend", "s3_bucket"))
    )

    assert state.backend is not original
    assert state.backend.backend_id == constants.BackendId.S3
    assert state.backend.bucket == _BUCKET


@pytest.mark.anyio
async def test_settings_reload_for_another_module_leaves_the_backend_alone(app):
    from settings.contracts.events import SettingsReloaded

    state = app.state.file_storage
    original = state.backend

    await app.state.sm.event_bus.publish(
        SettingsReloaded(package="users", changed=("oauth_microsoft_client_id",))
    )

    assert state.backend is original
