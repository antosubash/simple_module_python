"""Provider presets — per-IdP defaults layered onto OidcSettings.

A preset fills in claim names and (optionally) derives the discovery URL so a
well-known provider needs only a handful of env vars. ``generic`` is the
fallback for any OIDC-compliant IdP given an explicit discovery URL.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    """Defaults applied to unset OidcSettings fields for a named provider."""

    name: str
    # Template filled with ``tenant_id`` to derive the discovery URL when one is
    # not supplied explicitly. Empty ⇒ discovery URL must be configured directly.
    discovery_url_template: str = ""
    uid_claim: str = "sub"
    username_claim: str = "preferred_username"
    email_claim: str = "email"
    name_claim: str = "name"
    roles_claim_path: str = ""
    scope: str = "openid email profile"

    def discovery_url(self, tenant_id: str) -> str:
        """Render the discovery URL from ``tenant_id`` (empty if not templated)."""
        if not self.discovery_url_template:
            return ""
        return self.discovery_url_template.format(tenant_id=tenant_id)


PRESETS: dict[str, Preset] = {
    # Microsoft Entra ID (Azure AD), v2.0 endpoints. Single-tenant: the tenant
    # GUID (or a verified domain) goes in ``tenant_id``. App roles arrive in the
    # ``roles`` claim; ``oid`` is the stable per-tenant user object id.
    "entra": Preset(
        name="entra",
        discovery_url_template=(
            "https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration"
        ),
        uid_claim="oid",
        roles_claim_path="roles",
    ),
    # Any OIDC-compliant provider (Auth0, Okta, Zitadel, Authentik, Keycloak, ...)
    # configured with an explicit ``discovery_url``.
    "generic": Preset(name="generic"),
}


def get_preset(name: str) -> Preset:
    """Return the named preset, falling back to ``generic`` for unknown names."""
    return PRESETS.get(name, PRESETS["generic"])
