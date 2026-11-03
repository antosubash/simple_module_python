"""OIDC module settings -- DB-backed via ``register_module_settings``.

Configuration is preset-driven: pick a ``provider`` preset (e.g. ``entra``) and
supply the few required secrets; the preset fills claim defaults and derives the
discovery URL. ``generic`` works with any OIDC provider given a ``discovery_url``.
"""

from __future__ import annotations

import os

from pydantic import Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict
from simple_module_core.dotenv import env_str
from simple_module_core.environments import NON_PROD_ENVIRONMENTS
from simple_module_core.redirect_safety import non_empty_redirect
from simple_module_core.settings_base import DbBackedSettings
from simple_module_core.stored_settings import field_error

from oidc.constants import DEFAULT_LOGIN_REDIRECT_URL
from oidc.presets import get_preset

# Sentinel for "unset by the user" so the preset can supply a default while still
# letting an explicit empty/other value win.
_UNSET = "__unset__"


class OidcSettings(DbBackedSettings):
    """Generic OIDC configuration with per-provider presets."""

    model_config = SettingsConfigDict(extra="ignore")

    provider: str = Field(
        default=env_str("SM_OIDC_PROVIDER", "generic"), json_schema_extra={"requires_restart": True}
    )

    # Endpoint discovery. ``discovery_url`` wins; otherwise the preset derives it
    # from ``tenant_id`` (Entra). The well-known doc supplies all endpoints + issuer.
    discovery_url: str = Field(
        default=env_str("SM_OIDC_DISCOVERY_URL", ""), json_schema_extra={"requires_restart": True}
    )
    tenant_id: str = Field(
        default=env_str("SM_OIDC_TENANT_ID", ""), json_schema_extra={"requires_restart": True}
    )

    client_id: str = Field(
        default=env_str("SM_OIDC_CLIENT_ID", ""), json_schema_extra={"requires_restart": True}
    )
    client_secret: str = Field(
        default=env_str("SM_OIDC_CLIENT_SECRET", ""), json_schema_extra={"requires_restart": True}
    )

    # Bearer authentication is opt-in; browser ID tokens always use client_id.
    api_audience: str = ""
    # Clients (``azp``, or ``appid`` on Entra v1 tokens) allowed to call the API
    # with a bearer token, besides ``client_id``. An API token is minted for our
    # audience but by any client the IdP lets ask for it, so name each one.
    api_allowed_client_ids: list[str] = Field(default_factory=list)
    trust_tenant_claim: bool = False

    # Claim mapping. ``_UNSET`` defaults are replaced by the preset's value.
    scope: str = _UNSET
    uid_claim: str = _UNSET
    username_claim: str = _UNSET
    email_claim: str = _UNSET
    name_claim: str = _UNSET
    # Env-seedable: the first admin can only sign in once roles are mapped, and
    # the Settings UI that edits this needs an admin. A stored value still wins.
    roles_claim_path: str = env_str("SM_OIDC_ROLES_CLAIM_PATH", _UNSET)

    login_redirect_url: str = DEFAULT_LOGIN_REDIRECT_URL
    jwks_cache_ttl_seconds: int = Field(
        default=3600, ge=0, json_schema_extra={"requires_restart": True}
    )

    role_mapping: dict[str, str] = Field(
        default_factory=lambda: {"admin": "admin", "user": "user"},
    )

    @field_validator("login_redirect_url")
    @classmethod
    def _non_empty_redirect(cls, value: str) -> str:
        return non_empty_redirect(value, default=DEFAULT_LOGIN_REDIRECT_URL)

    @model_validator(mode="after")
    def _apply_preset(self) -> OidcSettings:
        preset = get_preset(self.provider)
        if self.provider == "entra":
            from urllib.parse import urlsplit

            forbidden = {"common", "organizations", "consumers"}
            segments = urlsplit(self.discovery_url).path.lower().split("/")
            if self.tenant_id.strip().lower() in forbidden or forbidden.intersection(segments):
                raise ValueError("Entra supports single-tenant configuration only")
        for name in (
            "uid_claim",
            "username_claim",
            "email_claim",
            "name_claim",
            "roles_claim_path",
            "scope",
        ):
            if getattr(self, name) == _UNSET:
                setattr(self, name, getattr(preset, name))
        if not self.discovery_url and self.tenant_id:
            self.discovery_url = preset.discovery_url(self.tenant_id)
        return self

    @model_validator(mode="after")
    def _check_required_in_production(self) -> OidcSettings:
        env = os.environ.get("SM_ENVIRONMENT", "development")
        if env in NON_PROD_ENVIRONMENTS:
            return self
        required = ("discovery_url", "client_id", "client_secret")
        missing = [field for field in required if not getattr(self, field)]
        if missing:
            raise field_error(
                type(self),
                missing[0],
                "oidc_settings_required",
                f"OIDC settings required in production: {', '.join(missing)}",
                value="",
                related=list(required),
            )
        return self
