"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for the SimpleModule host application.

    All settings can be overridden via environment variables prefixed with ``SM_``.
    """

    model_config = SettingsConfigDict(env_prefix="SM_", env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite+aiosqlite:///./app.db"

    # Keycloak
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "simple-module"
    keycloak_client_id: str = "simple-module-app"
    keycloak_client_secret: str = ""

    # App
    environment: str = "development"
    secret_key: str = "change-me-in-production"
    vite_dev_url: str = "http://localhost:5173"
    debug: bool = False

    @property
    def is_development(self) -> bool:
        return self.environment == "development"
