"""Settings module's own configuration (DB-backed)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsSettings(BaseSettings):
    """Configuration for the Settings module."""

    model_config = SettingsConfigDict(extra="ignore")
