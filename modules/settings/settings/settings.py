"""Settings module's own configuration (DB-backed)."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict
from simple_module_core.settings_base import DbBackedSettings


class SettingsSettings(DbBackedSettings):
    """Configuration for the Settings module."""

    # ``DbBackedSettings`` (not ``BaseSettings``) so the DB is genuinely the
    # only source: omitting ``env_prefix`` would leave pydantic-settings
    # reading each field from its bare name — GH #283.
    model_config = SettingsConfigDict(extra="ignore")
