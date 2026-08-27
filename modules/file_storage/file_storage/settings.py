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

from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict
from simple_module_core.settings_base import DbBackedSettings

from file_storage import constants


class FileStorageSettings(DbBackedSettings):
    """Configuration for the file_storage module.

    The active backend is selected by ``backend`` (matches a key in the
    backend registry). All ``s3_*`` fields are optional unless ``backend``
    selects S3, in which case the validator below enforces presence of
    bucket + region. Custom backends supply their own validation by
    subclassing or by reading additional fields at registration time.
    """

    # ``DbBackedSettings`` (not ``BaseSettings``) so the DB is genuinely the
    # only source: omitting ``env_prefix`` would leave pydantic-settings
    # reading each field from its bare name — GH #283.
    model_config = SettingsConfigDict(extra="ignore")

    backend: str = constants.DEFAULT_BACKEND

    # Filesystem backend
    fs_root_path: str = Field(
        default=constants.DEFAULT_FS_ROOT,
        json_schema_extra={"group": "Filesystem"},
    )

    # S3-compatible backend (works with AWS S3, MinIO, R2, etc.)
    s3_bucket: str = Field(default="", json_schema_extra={"group": "S3"})
    s3_region: str = Field(default="", json_schema_extra={"group": "S3"})
    s3_access_key_id: str = Field(default="", json_schema_extra={"group": "S3"})
    s3_secret_access_key: str = Field(default="", json_schema_extra={"group": "S3"})
    s3_endpoint_url: str = Field(
        default="",
        json_schema_extra={"group": "S3"},
        description="Custom endpoint for MinIO / R2. Blank uses AWS default.",
    )
    s3_presign_ttl_seconds: int = Field(
        default=constants.DEFAULT_PRESIGN_TTL_SECONDS,
        json_schema_extra={"group": "S3"},
    )

    # Limits
    max_file_size_bytes: int = constants.DEFAULT_MAX_FILE_SIZE_BYTES
    allowed_content_types: list[str] | None = Field(
        default=None,
        description="Whitelist of MIME types. None = any type allowed.",
    )

    @model_validator(mode="after")
    def _validate_backend_config(self) -> FileStorageSettings:
        """Enforce per-backend required fields.

        We validate at config time rather than at backend construction so
        misconfigured prod boots fail fast with a clear message instead of
        deferring the error until the first upload.
        """
        if self.backend == constants.BackendId.S3:
            missing = [
                name
                for name, value in (
                    ("s3_bucket", self.s3_bucket),
                    ("s3_region", self.s3_region),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"S3 backend selected but {', '.join(missing)} is not set.")
        return self

    def resolved_fs_root(self) -> Path:
        """Return ``fs_root_path`` as an absolute Path."""
        return Path(self.fs_root_path).expanduser().resolve()
