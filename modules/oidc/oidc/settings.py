"""OIDC module settings -- DB-backed via ``register_module_settings``.

Configuration is preset-driven: pick a ``provider`` preset (e.g. ``entra``) and
supply the few required secrets; the preset fills claim defaults and derives the
discovery URL. ``generic`` works with any OIDC provider given a ``discovery_url``.
"""

from __future__ import annotations

import os

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.dotenv import env_str
from simple_module_core.environments import NON_PROD_ENVIRONMENTS

from oidc.presets import get_preset

# Sentinel for "unset by the user" so the preset can supply a default while still
# letting an explicit empty/other value win.
_UNSET = "__unset__"


class OidcSettings(BaseSettings):
    """Generic OIDC configuration with per-provider presets."""

    model_config = SettingsConfigDict(extra="ignore")

    provider: str = env_str("SM_OIDC_PROVIDER", "generic")

    # Endpoint discovery. ``discovery_url`` wins; otherwise the preset derives it
    # from ``tenant_id`` (Entra). The well-known doc supplies all endpoints + issuer.
    discovery_url: str = env_str("SM_OIDC_DISCOVERY_URL", "")
    tenant_id: str = env_str("SM_OIDC_TENANT_ID", "")

    client_id: str = env_str("SM_OIDC_CLIENT_ID", "")
    client_secret: str = env_str("SM_OIDC_CLIENT_SECRET", "")

    # Audience for JWT validation. Empty ⇒ falls back to ``client_id``.
    audience: str = env_str("SM_OIDC_AUDIENCE", "")

    # Claim mapping. ``_UNSET`` defaults are replaced by the preset's value.
    scope: str = env_str("SM_OIDC_SCOPE", _UNSET)
    uid_claim: str = env_str("SM_OIDC_UID_CLAIM", _UNSET)
    username_claim: str = env_str("SM_OIDC_USERNAME_CLAIM", _UNSET)
    email_claim: str = env_str("SM_OIDC_EMAIL_CLAIM", _UNSET)
    name_claim: str = env_str("SM_OIDC_NAME_CLAIM", _UNSET)
    roles_claim_path: str = env_str("SM_OIDC_ROLES_CLAIM_PATH", _UNSET)

    login_redirect_url: str = "/dashboard/"
    jwks_cache_ttl_seconds: int = 3600

    role_mapping: dict[str, str] = Field(
        default_factory=lambda: {"admin": "admin", "user": "user"},
    )

    @property
    def jwt_audience(self) -> str:
        """Audience to validate tokens against (explicit override or client_id)."""
        return self.audience or self.client_id

    @model_validator(mode="after")
    def _apply_preset(self) -> OidcSettings:
        preset = get_preset(self.provider)
        if self.uid_claim == _UNSET:
            self.uid_claim = preset.uid_claim
        if self.username_claim == _UNSET:
            self.username_claim = preset.username_claim
        if self.email_claim == _UNSET:
            self.email_claim = preset.email_claim
        if self.name_claim == _UNSET:
            self.name_claim = preset.name_claim
        if self.roles_claim_path == _UNSET:
            self.roles_claim_path = preset.roles_claim_path
        if self.scope == _UNSET:
            self.scope = preset.scope
        if not self.discovery_url and self.tenant_id:
            self.discovery_url = preset.discovery_url(self.tenant_id)
        return self

    @model_validator(mode="after")
    def _check_required_in_production(self) -> OidcSettings:
        env = os.environ.get("SM_ENVIRONMENT", "development")
        if env in NON_PROD_ENVIRONMENTS:
            return self
        missing = []
        if not self.discovery_url:
            missing.append("SM_OIDC_DISCOVERY_URL (or SM_OIDC_TENANT_ID for a templated preset)")
        if not self.client_id:
            missing.append("SM_OIDC_CLIENT_ID")
        if not self.client_secret:
            missing.append("SM_OIDC_CLIENT_SECRET")
        if missing:
            msg = f"OIDC settings required in production: {', '.join(missing)}"
            raise ValueError(msg)
        return self
