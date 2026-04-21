"""Datasets module settings loaded from SM_DATASETS_* environment variables.

Bytes storage is delegated to the ``file_storage`` module — its
``SM_FILE_STORAGE_*`` variables (backend, FS root, S3 bucket, etc.) are
the single source of truth. Datasets owns only its catalog-specific knobs.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from datasets import constants


class DatasetsSettings(BaseSettings):
    """Configuration for the datasets catalog."""

    model_config = SettingsConfigDict(
        env_prefix=constants.ENV_PREFIX,
        env_file=".env",
        extra="ignore",
    )

    max_upload_mb: int = Field(
        default=constants.DEFAULT_MAX_UPLOAD_MB,
        gt=0,
        description="Maximum upload size per dataset in megabytes.",
    )
