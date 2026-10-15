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
from pydantic_settings import SettingsConfigDict
from simple_module_core.settings_base import DbBackedSettings

from file_storage import constants

# "s3" is SigV2, kept only for legacy S3-compatible stores that lack SigV4.
_SIGNATURE_VERSIONS = frozenset({"s3v4", "s3"})


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
    s3_public_endpoint_url: str = Field(
        default="",
        json_schema_extra={"group": "S3"},
        description=(
            "Browser-facing S3 endpoint used to presign direct part uploads, when it "
            "differs from s3_endpoint_url (e.g. an internal MinIO hostname). Blank "
            "falls back to s3_endpoint_url. Its origin is added to CSP connect-src."
        ),
    )
    s3_signature_version: str = Field(
        default="s3v4",
        json_schema_extra={"group": "S3"},
        description="Presign signature version. Keep s3v4; SigV2 is rejected by most providers.",
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
    # Reported, not enforced: the browse screen states "1.2 GB of 5 GB used"
    # only for installs that have said what 5 GB means to them. Left unset,
    # the screen reports usage without inventing a ceiling, and uploads are
    # bounded by ``max_file_size_bytes`` alone as before.
    quota_bytes: int | None = Field(
        default=None,
        description="Total storage the browse screen measures usage against. None = unmeasured.",
    )

    # Resumable / direct uploads (#454)
    direct_upload_threshold_bytes: int = Field(
        default=constants.DEFAULT_DIRECT_UPLOAD_THRESHOLD_BYTES,
        gt=0,
        description="Files larger than this upload in parts through a resumable session.",
    )
    max_direct_upload_bytes: int = Field(
        default=constants.DEFAULT_MAX_DIRECT_UPLOAD_BYTES,
        gt=0,
        description="Largest file the resumable session flow accepts.",
    )
    multipart_part_size_bytes: int = Field(
        default=constants.DEFAULT_PART_SIZE_BYTES,
        ge=constants.MIN_PART_SIZE_BYTES,
        description="Preferred part size; grown automatically to stay under 10,000 parts.",
    )
    upload_session_ttl_seconds: int = Field(
        default=constants.DEFAULT_UPLOAD_SESSION_TTL_SECONDS,
        gt=0,
        description="How long an unfinished upload session stays resumable.",
    )

    @field_validator("s3_signature_version")
    @classmethod
    def _known_signature_version(cls, value: str) -> str:
        # botocore only fails on an unknown version when the first client is
        # built, so an admin-UI typo would otherwise surface as failed uploads.
        if value not in _SIGNATURE_VERSIONS:
            raise ValueError(f"s3_signature_version must be one of {sorted(_SIGNATURE_VERSIONS)}")
        return value

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

    def presign_endpoint_url(self) -> str:
        """The endpoint browsers reach: ``s3_public_endpoint_url``, else ``s3_endpoint_url``."""
        return self.s3_public_endpoint_url or self.s3_endpoint_url

    def resolved_fs_root(self) -> Path:
        """Return ``fs_root_path`` as an absolute Path."""
        return Path(self.fs_root_path).expanduser().resolve()
