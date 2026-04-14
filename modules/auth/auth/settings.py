"""Auth module settings loaded from SM_AUTH_* environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    """Keycloak OAuth configuration for the auth module."""

    model_config = SettingsConfigDict(env_prefix="SM_AUTH_", env_file=".env", extra="ignore")

    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "simple-module"
    keycloak_client_id: str = "simple-module-app"
    keycloak_client_secret: str = ""
