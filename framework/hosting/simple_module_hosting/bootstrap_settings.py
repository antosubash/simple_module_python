"""Env-only settings read before the database is available.

Everything here is needed either to connect to the DB, sign session cookies,
or configure the Python process (logging, Vite asset URLs, module allowlist).
These values stay in ``.env`` — all other settings live in the DB.
"""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.environments import NON_PROD_ENVIRONMENTS

_PLACEHOLDER_SECRET_KEY = "change-me-in-production"


class BootstrapSettings(BaseSettings):
    """Pre-DB bootstrap environment knobs."""

    model_config = SettingsConfigDict(env_prefix="SM_", env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./app.db"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_pre_ping: bool = True
    db_pool_recycle: int = 1800

    environment: str = "development"
    secret_key: str = _PLACEHOLDER_SECRET_KEY
    vite_dev_url: str = "http://localhost:5050"
    debug: bool = False

    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    modules_enabled: list[str] | None = None

    auth_public_paths: list[str] = []
    """Host-level anonymous-access path prefixes (``SM_AUTH_PUBLIC_PATHS``).

    An escape hatch for exposing a route without a session when no module owns
    it. Each entry is treated as a prefix rule and seeded into the
    ``PublicRouteRegistry`` at boot. Modules should prefer the
    ``register_public_routes`` hook, which is method-aware.
    """

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @model_validator(mode="after")
    def _forbid_placeholder_secret_in_production(self) -> BootstrapSettings:
        if (
            self.environment not in NON_PROD_ENVIRONMENTS
            and self.secret_key == _PLACEHOLDER_SECRET_KEY
        ):
            raise ValueError(
                f"SM_SECRET_KEY must be set to a non-default value when "
                f"SM_ENVIRONMENT={self.environment!r}. Generate one with "
                "`python -c 'import secrets; print(secrets.token_urlsafe(48))'`."
            )
        return self
