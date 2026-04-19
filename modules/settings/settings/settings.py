"""Settings module configuration loaded from SM_SETTINGS_* environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsSettings(BaseSettings):
    """Configuration for the Settings module."""

    model_config = SettingsConfigDict(env_prefix="SM_SETTINGS_", env_file=".env", extra="ignore")
