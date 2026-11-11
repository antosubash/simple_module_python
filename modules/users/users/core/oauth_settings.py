"""OAuth / OIDC provider settings, the base of :class:`UsersSettings`.

Split out of ``settings.py`` so the provider fields and their checks sit
together; ``UsersSettings`` inherits every field here, so callers keep reading
them from ``app.state.users.settings``.
"""

from __future__ import annotations

import logging
import uuid

from pydantic import Field, field_validator, model_validator
from simple_module_core.settings_base import DbBackedSettings

from users.core.constants import ADMIN_ROLE_NAME

logger = logging.getLogger("users.settings")

# The ``{provider}`` URL segments ``users.oauth.providers.build_clients`` can serve.
OAUTH_PROVIDER_NAMES = frozenset({"google", "github", "microsoft", "oidc"})
OAUTH_PROVISIONING_GROUP = "OAuth provisioning"

# Microsoft's fixed "consumers" tenant (personal accounts): a GUID, but not one directory.
MICROSOFT_CONSUMERS_TENANT = uuid.UUID("9188040d-6c67-4c5b-b112-36a304b66dad")


def is_tenant_guid(tenant: str) -> bool:
    """Whether a Microsoft ``tenant`` pins one work/school directory (a canonical GUID).

    ``common`` & co, non-canonical spellings and the personal-account ``consumers``
    tenant GUID do not qualify.
    """
    try:
        parsed = uuid.UUID(tenant)
    except ValueError:
        return False
    return str(parsed) == tenant.lower() and parsed != MICROSOFT_CONSUMERS_TENANT


class OAuthSettings(DbBackedSettings):
    """Provider credentials and SSO policy for the ``users`` module."""

    # OAuth / OIDC providers — configured via the admin settings UI
    # (/settings/modules → Users). Credentials live in the DB-backed settings
    # store and hydrate after boot; secret fields are masked in the UI (the
    # same treatment the SMTP password gets). Provider changes apply live via
    # the SettingsReloaded event — no restart (see users/module.py).
    oauth_google_client_id: str = Field(default="", json_schema_extra={"group": "Google OAuth"})
    oauth_google_client_secret: str = Field(default="", json_schema_extra={"group": "Google OAuth"})
    oauth_github_client_id: str = Field(default="", json_schema_extra={"group": "GitHub OAuth"})
    oauth_github_client_secret: str = Field(default="", json_schema_extra={"group": "GitHub OAuth"})
    # Generic OIDC — any provider that exposes a discovery URL
    # (Keycloak, Authentik, Auth0, Zitadel, ...).
    oauth_oidc_client_id: str = Field(default="", json_schema_extra={"group": "OIDC"})
    oauth_oidc_client_secret: str = Field(default="", json_schema_extra={"group": "OIDC"})
    oauth_oidc_discovery_url: str = Field(default="", json_schema_extra={"group": "OIDC"})
    oauth_oidc_display_name: str = Field(default="OIDC", json_schema_extra={"group": "OIDC"})
    # Microsoft Entra ID / Microsoft accounts. tenant: "common" (any work/school
    # or personal account), "organizations" (work/school only), or a tenant GUID
    # to restrict sign-in to a single Entra tenant.
    oauth_microsoft_client_id: str = Field(
        default="", json_schema_extra={"group": "Microsoft OAuth"}
    )
    oauth_microsoft_client_secret: str = Field(
        default="", json_schema_extra={"group": "Microsoft OAuth"}
    )
    oauth_microsoft_tenant: str = Field(
        default="common", json_schema_extra={"group": "Microsoft OAuth"}
    )
    # Treat a member account's userPrincipalName as a verified email, so it
    # links to an invited or verified local account (#873). Only effective when
    # the tenant is a GUID: that tenant verified the UPN's domain. Guest UPNs
    # (``#EXT#``) stay unverified.
    oauth_microsoft_trust_tenant_upn: bool = Field(
        default=False, json_schema_extra={"group": "Microsoft OAuth"}
    )

    @model_validator(mode="after")
    def _warn_on_ignored_microsoft_trust(self) -> OAuthSettings:
        """The UPN trust policy is inert unless one tenant is pinned by GUID."""
        if self.oauth_microsoft_trust_tenant_upn and not is_tenant_guid(
            self.oauth_microsoft_tenant
        ):
            logger.warning(
                "users.oauth.microsoft_trust_ignored — oauth_microsoft_trust_tenant_upn is on "
                "but oauth_microsoft_tenant=%r is not one work/school tenant GUID; Microsoft "
                "emails stay unverified. Set it to your directory's GUID to trust member UPNs.",
                self.oauth_microsoft_tenant,
            )
        return self

    # Providers that may create an account on first sign-in with ``allow_signup``
    # off (#874), and only when the provider proved the email. Local email and
    # password registration keeps following ``allow_signup`` alone.
    oauth_signup_providers: list[str] = Field(
        default_factory=list, json_schema_extra={"group": OAUTH_PROVISIONING_GROUP}
    )
    # Role for accounts those providers create. Blank: no role until an admin
    # grants one. A name with no matching role is logged and grants nothing.
    oauth_signup_default_role: str = Field(
        default="", json_schema_extra={"group": OAUTH_PROVISIONING_GROUP}
    )

    @field_validator("oauth_signup_providers")
    @classmethod
    def _known_signup_providers(cls, value: list[str]) -> list[str]:
        value = [name.strip().lower() for name in value]
        unknown = sorted(set(value) - OAUTH_PROVIDER_NAMES)
        if unknown:
            known = sorted(OAUTH_PROVIDER_NAMES)
            raise ValueError(f"unknown OAuth provider(s) {unknown}; expected any of {known}")
        return value

    @field_validator("oauth_signup_default_role")
    @classmethod
    def _no_admin_provisioning(cls, value: str) -> str:
        """Auto-granting admin to a provider's whole user base is never the intent."""
        value = value.strip()
        if value.lower() == ADMIN_ROLE_NAME:
            raise ValueError("SSO-provisioned accounts cannot get the admin role automatically")
        return value
