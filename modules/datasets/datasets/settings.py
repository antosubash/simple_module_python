"""Datasets module settings (DB-backed).

Construction no longer reads ``SM_DATASETS_*`` environment variables.
Values come from pydantic defaults at boot, then get hydrated from the DB
by the hosting lifespan before module ``on_startup`` runs. Runtime changes
go through ``settings.reload.apply_changes_and_reload``.

Bytes storage is delegated to the ``file_storage`` module — its own
settings (backend, FS root, S3 bucket, etc.) are the single source of
truth. Datasets owns only its catalog-specific knobs.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from datasets import constants


class DatasetsSettings(BaseSettings):
    """Configuration for the datasets catalog."""

    model_config = SettingsConfigDict(extra="ignore")

    max_upload_mb: int = Field(
        default=constants.DEFAULT_MAX_UPLOAD_MB,
        gt=0,
        description="Maximum upload size per dataset in megabytes.",
    )
