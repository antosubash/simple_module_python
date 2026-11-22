"""Keycloak module settings -- DB-backed via ``register_module_settings``."""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict
from simple_module_core.dotenv import env_bool, env_str
from simple_module_core.environments import NON_PROD_ENVIRONMENTS
from simple_module_core.settings_base import DbBackedSettings
from simple_module_core.stored_settings import field_error


class KeycloakSettings(DbBackedSettings):
    """Keycloak OIDC configuration."""

    # ``DbBackedSettings`` (not ``BaseSettings``) so the DB is genuinely the
    # only source: omitting ``env_prefix`` would leave pydantic-settings
    # reading each field from its bare name — GH #283.
    model_config = SettingsConfigDict(extra="ignore")

    server_url: str = Field(
        default=env_str("SM_KEYCLOAK_SERVER_URL", ""), json_schema_extra={"requires_restart": True}
    )
    realm: str = Field(
        default=env_str("SM_KEYCLOAK_REALM", ""), json_schema_extra={"requires_restart": True}
    )
    client_id: str = Field(
        default=env_str("SM_KEYCLOAK_CLIENT_ID", ""), json_schema_extra={"requires_restart": True}
    )
    client_secret: str = Field(
        default=env_str("SM_KEYCLOAK_CLIENT_SECRET", ""),
        json_schema_extra={"requires_restart": True},
    )

    # Off by default: the JWT ``tenant_id`` claim is only as trustworthy as the
    # realm mapper that produces it. A mapper reading an attribute the user can
    # edit lets them name their own tenant. Turn on only for a realm whose
    # protocol mapper users cannot influence; the ``tenants`` module's
    # resolver ignores the claim either way.
    trust_tenant_claim: bool = env_bool("SM_KEYCLOAK_TRUST_TENANT_CLAIM", False)

    roles_claim_path: str = "realm_access.roles"
    jwks_cache_ttl_seconds: int = Field(
        default=3600, ge=0, json_schema_extra={"requires_restart": True}
    )

    role_mapping: dict[str, str] = Field(
        default_factory=lambda: {"admin": "admin", "user": "user"},
    )

    @model_validator(mode="after")
    def _check_required_in_production(self) -> KeycloakSettings:
        import os

        env = os.environ.get("SM_ENVIRONMENT", "development")
        if env in NON_PROD_ENVIRONMENTS:
            return self
        required = (
            ("server_url", "SM_KEYCLOAK_SERVER_URL"),
            ("realm", "SM_KEYCLOAK_REALM"),
            ("client_id", "SM_KEYCLOAK_CLIENT_ID"),
            ("client_secret", "SM_KEYCLOAK_CLIENT_SECRET"),
        )
        missing = [(field, var) for field, var in required if not getattr(self, field)]
        if missing:
            # Located on the first empty field so the form shows it there.
            msg = f"Keycloak settings required in production: {', '.join(v for _, v in missing)}"
            raise field_error(
                type(self),
                missing[0][0],
                "keycloak_settings_required",
                msg,
                value="",
                related=[field for field, _ in required],
            )
        return self
