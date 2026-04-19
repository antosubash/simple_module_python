"""Datasets module settings loaded from SM_DATASETS_* environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatasetsSettings(BaseSettings):
    """Configuration for the GIS datasets catalog."""

    model_config = SettingsConfigDict(
        env_prefix="SM_DATASETS_",
        env_file=".env",
        extra="ignore",
    )

    storage_dir: str = Field(
        default="./var/datasets",
        description="Filesystem directory for uploaded dataset files.",
    )
    max_upload_mb: int = Field(
        default=256,
        gt=0,
        description="Maximum upload size per dataset in megabytes.",
    )
