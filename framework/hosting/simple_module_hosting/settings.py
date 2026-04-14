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

    @property
    def is_development(self) -> bool:
        return self.environment == "development"
