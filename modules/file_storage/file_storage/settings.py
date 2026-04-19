"""file_storage settings loaded from SM_FILE_STORAGE_* environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from file_storage import constants


class FileStorageSettings(BaseSettings):
    """Configuration for the file_storage module.

    The active backend is selected by ``backend`` (matches a key in the
    backend registry). All ``s3_*`` fields are optional unless ``backend``
    selects S3, in which case the validator below enforces presence of
    bucket + region. Custom backends supply their own validation by
    subclassing or by reading additional env vars at registration time.
    """

    model_config = SettingsConfigDict(
        env_prefix=constants.ENV_PREFIX,
        env_file=".env",
        extra="ignore",
    )

    backend: str = constants.DEFAULT_BACKEND

    # Filesystem backend
    fs_root_path: str = constants.DEFAULT_FS_ROOT

    # S3-compatible backend (works with AWS S3, MinIO, R2, etc.)
    s3_bucket: str = ""
    s3_region: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_endpoint_url: str = ""  # custom endpoint for MinIO / R2
    s3_presign_ttl_seconds: int = constants.DEFAULT_PRESIGN_TTL_SECONDS

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
                    (f"{constants.ENV_PREFIX}S3_BUCKET", self.s3_bucket),
                    (f"{constants.ENV_PREFIX}S3_REGION", self.s3_region),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"S3 backend selected but {', '.join(missing)} is not set.")
        return self

    def resolved_fs_root(self) -> Path:
        """Return ``fs_root_path`` as an absolute Path."""
        return Path(self.fs_root_path).expanduser().resolve()
