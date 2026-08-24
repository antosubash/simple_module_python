"""file_storage module settings (DB-backed).

Construction no longer reads ``SM_FILE_STORAGE_*`` environment variables.
Values come from pydantic defaults at boot, then get hydrated from the DB
by the hosting lifespan before module ``on_startup`` runs. Runtime changes
go through ``settings.reload.apply_changes_and_reload``.

Fields are grouped via ``json_schema_extra={"group": ...}`` so the admin UI
can render them under their respective backend sections.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from file_storage import constants

_ALLOWED_ADDRESSING_STYLES = frozenset(
    {
        constants.AddressingStyle.AUTO,
        constants.AddressingStyle.PATH,
        constants.AddressingStyle.VIRTUAL,
    }
)


class FileStorageSettings(BaseSettings):
    """Configuration for the file_storage module.

    The active backend is selected by ``backend`` (matches a key in the
    backend registry). All ``s3_*`` fields are optional unless ``backend``
    selects S3, in which case the validator below enforces presence of
    bucket + region. Custom backends supply their own validation by
    subclassing or by reading additional fields at registration time.
    """

    model_config = SettingsConfigDict(extra="ignore")

    backend: str = Field(default=constants.DEFAULT_BACKEND, json_schema_extra={"group": "General"})

    key_prefix: str = Field(
        default=constants.DEFAULT_KEY_PREFIX,
        json_schema_extra={"group": "General"},
        description=(
            "Folder every object is stored under, e.g. 'media/'. "
            "Blank stores at the bucket root. Applies to all backends. "
            "Changing it only affects new uploads — existing files keep working."
        ),
    )

    # Filesystem backend
    fs_root_path: str = Field(
        default=constants.DEFAULT_FS_ROOT,
        json_schema_extra={"group": "Filesystem"},
    )

    # S3-compatible backend (works with AWS S3, MinIO, R2, etc.)
    s3_bucket: str = Field(default="", json_schema_extra={"group": "S3"})
    s3_region: str = Field(
        default=constants.DEFAULT_S3_REGION,
        json_schema_extra={"group": "S3"},
        description="Region name. Providers that ignore regions (R2) accept 'auto'.",
    )
    s3_access_key_id: str = Field(default="", json_schema_extra={"group": "S3"})
    s3_secret_access_key: str = Field(default="", json_schema_extra={"group": "S3"})
    s3_endpoint_url: str = Field(
        default="",
        json_schema_extra={"group": "S3"},
        description="Custom endpoint for MinIO / R2. Blank uses AWS default.",
    )
    s3_public_endpoint_url: str = Field(
        default="",
        json_schema_extra={"group": "S3"},
        description=(
            "Host used to sign download URLs, when it differs from the endpoint "
            "the app itself connects to (e.g. app reaches MinIO at "
            "http://minio:9000 but browsers need https://files.example.com). "
            "Blank signs against the regular endpoint."
        ),
    )
    s3_addressing_style: str = Field(
        default=constants.DEFAULT_ADDRESSING_STYLE,
        json_schema_extra={"group": "S3"},
        description=(
            "'auto', 'path', or 'virtual'. Use 'path' for MinIO, Ceph, and any "
            "endpoint addressed by IP or localhost."
        ),
    )
    s3_signature_version: str = Field(
        default="",
        json_schema_extra={"group": "S3"},
        description="Override the signing algorithm, e.g. 's3v4'. Blank uses the default.",
    )
    s3_verify_ssl: bool = Field(
        default=True,
        json_schema_extra={"group": "S3"},
        description="Set false only for internal gateways with self-signed certificates.",
    )
    s3_presign_ttl_seconds: int = Field(
        default=constants.DEFAULT_PRESIGN_TTL_SECONDS,
        json_schema_extra={"group": "S3"},
    )

    # Limits
    max_file_size_bytes: int = Field(
        default=constants.DEFAULT_MAX_FILE_SIZE_BYTES,
        json_schema_extra={"group": "Limits"},
    )
    allowed_content_types: list[str] | None = Field(
        default=None,
        json_schema_extra={"group": "Limits"},
        description="Whitelist of MIME types. None = any type allowed.",
    )

    @field_validator("key_prefix", mode="after")
    @classmethod
    def _normalise_key_prefix(cls, value: str) -> str:
        """Canonicalise the prefix to ``''`` or ``'a/b/'``.

        Operators type this by hand in the settings UI, so we accept the
        obvious variants (``media``, ``/media``, ``media/``, ``a//b``) rather
        than rejecting them. Traversal segments are rejected outright: with the
        filesystem backend a ``..`` would escape ``fs_root_path``, and the
        backend's own guard raises a generic StorageBackendError only at upload
        time — far too late to be actionable.
        """
        cleaned = value.strip().replace("\\", "/")
        segments = [part for part in cleaned.split("/") if part not in ("", ".")]
        if any(part == ".." for part in segments):
            raise ValueError(f"key_prefix must not contain '..' segments: {value!r}")
        if any(":" in part for part in segments):
            raise ValueError(f"key_prefix must be a relative folder path: {value!r}")
        return f"{'/'.join(segments)}/" if segments else ""

    @field_validator("s3_addressing_style", mode="after")
    @classmethod
    def _validate_addressing_style(cls, value: str) -> str:
        normalised = value.strip().lower()
        if normalised not in _ALLOWED_ADDRESSING_STYLES:
            raise ValueError(
                f"s3_addressing_style must be one of "
                f"{sorted(_ALLOWED_ADDRESSING_STYLES)}, got {value!r}."
            )
        return normalised

    @model_validator(mode="after")
    def _validate_backend_config(self) -> FileStorageSettings:
        """Enforce per-backend required fields.

        We validate at config time rather than at backend construction so
        misconfigured prod boots fail fast with a clear message instead of
        deferring the error until the first upload.

        Only the bucket is genuinely required: a region always has a usable
        default, since providers that ignore regions still need a filler string
        for SigV4 rather than a correct one.
        """
        if self.backend == constants.BackendId.S3 and not self.s3_bucket:
            raise ValueError("S3 backend selected but s3_bucket is not set.")
        return self

    def resolved_fs_root(self) -> Path:
        """Return ``fs_root_path`` as an absolute Path."""
        return Path(self.fs_root_path).expanduser().resolve()
