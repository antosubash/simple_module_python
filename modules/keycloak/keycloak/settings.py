"""Keycloak module settings -- DB-backed via ``register_module_settings``."""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.dotenv import env_str
from simple_module_core.environments import NON_PROD_ENVIRONMENTS


class KeycloakSettings(BaseSettings):
    """Keycloak OIDC configuration."""

    model_config = SettingsConfigDict(extra="ignore")

    server_url: str = env_str("SM_KEYCLOAK_SERVER_URL", "")
    realm: str = env_str("SM_KEYCLOAK_REALM", "")
    client_id: str = env_str("SM_KEYCLOAK_CLIENT_ID", "")
    client_secret: str = env_str("SM_KEYCLOAK_CLIENT_SECRET", "")

    roles_claim_path: str = "realm_access.roles"
    admin_role: str = "admin"
    login_redirect_url: str = "/dashboard/"
    jwks_cache_ttl_seconds: int = 3600

    role_mapping: dict[str, str] = Field(
        default_factory=lambda: {"admin": "admin", "user": "user"},
    )

    @model_validator(mode="after")
    def _check_required_in_production(self) -> KeycloakSettings:
        import os

        env = os.environ.get("SM_ENVIRONMENT", "development")
        if env in NON_PROD_ENVIRONMENTS:
            return self
        missing = []
        if not self.server_url:
            missing.append("SM_KEYCLOAK_SERVER_URL")
        if not self.realm:
            missing.append("SM_KEYCLOAK_REALM")
        if not self.client_id:
            missing.append("SM_KEYCLOAK_CLIENT_ID")
        if not self.client_secret:
            missing.append("SM_KEYCLOAK_CLIENT_SECRET")
        if missing:
            msg = f"Keycloak settings required in production: {', '.join(missing)}"
            raise ValueError(msg)
        return self
