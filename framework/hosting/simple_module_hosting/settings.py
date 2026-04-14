"""Application settings loaded from environment variables."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for the SimpleModule host application.

    All settings can be overridden via environment variables prefixed with ``SM_``.
    """

    model_config = SettingsConfigDict(env_prefix="SM_", env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite+aiosqlite:///./app.db"

    # App
    environment: str = "development"
    secret_key: str = "change-me-in-production"
    vite_dev_url: str = "http://localhost:5050"
    debug: bool = False

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # Module loading
    modules_enabled: list[str] | None = None
    """Optional allowlist of module names to load.

    When ``None`` (default), every installed module is loaded. When a list is
    provided (e.g. ``SM_MODULES_ENABLED='["Auth","Products"]'`` in env), only
    those modules are loaded — useful for staging rollouts, feature flags at
    the module level, or debugging isolation. Names are matched case-insensitively
    against ``ModuleMeta.name``.
    """

    @property
    def is_development(self) -> bool:
        return self.environment == "development"
