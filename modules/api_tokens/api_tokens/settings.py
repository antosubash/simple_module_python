"""api_tokens settings — DB-backed via ``register_module_settings``."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from simple_module_core.settings_base import DbBackedSettings


class ApiTokensSettings(DbBackedSettings):
    """Configuration for personal access tokens and service keys."""

    # ``DbBackedSettings`` so the DB is the only source (GH #283).
    model_config = SettingsConfigDict(extra="ignore")

    max_lifetime_days: int = Field(default=365, ge=1, le=3650)
    """The longest expiry a new token may be given. Existing tokens keep theirs."""
