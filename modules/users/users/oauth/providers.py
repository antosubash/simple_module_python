"""OAuth/OIDC provider client factory.

Constructs the ``httpx_oauth`` clients for every provider that has both
``client_id`` and ``client_secret`` set in :class:`UsersSettings`. A provider
with no credentials is silently skipped — that's the "feature flag" knob.

Lives in its own module so :func:`UsersModule.register_routes` can import it
without dragging the heavy ``httpx_oauth`` packages into the cold-start path
when no provider is configured.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from httpx_oauth.oauth2 import BaseOAuth2

    from users.settings import UsersSettings

logger = logging.getLogger(__name__)


class OAuthProvider(NamedTuple):
    """One configured provider — name is the URL segment (``/auth/<name>``)."""

    name: str
    display_name: str
    client: BaseOAuth2


def build_clients(settings: UsersSettings) -> list[OAuthProvider]:
    """Return one entry per provider that has both id and secret configured.

    The generic OIDC provider also requires a discovery URL. If discovery
    fetch fails at construction time, the provider is logged and skipped
    rather than raising — a misconfigured IdP must not break boot.
    """
    out: list[OAuthProvider] = []

    if settings.oauth_google_client_id and settings.oauth_google_client_secret:
        from httpx_oauth.clients.google import GoogleOAuth2

        out.append(
            OAuthProvider(
                "google",
                "Google",
                GoogleOAuth2(
                    settings.oauth_google_client_id,
                    settings.oauth_google_client_secret,
                ),
            )
        )

    if settings.oauth_github_client_id and settings.oauth_github_client_secret:
        from httpx_oauth.clients.github import GitHubOAuth2

        out.append(
            OAuthProvider(
                "github",
                "GitHub",
                GitHubOAuth2(
                    settings.oauth_github_client_id,
                    settings.oauth_github_client_secret,
                ),
            )
        )

    if settings.oauth_microsoft_client_id and settings.oauth_microsoft_client_secret:
        from httpx_oauth.clients.microsoft import MicrosoftGraphOAuth2

        out.append(
            OAuthProvider(
                "microsoft",
                "Microsoft",
                MicrosoftGraphOAuth2(
                    settings.oauth_microsoft_client_id,
                    settings.oauth_microsoft_client_secret,
                    tenant=settings.oauth_microsoft_tenant or "common",
                    name="microsoft",
                ),
            )
        )

    if (
        settings.oauth_oidc_client_id
        and settings.oauth_oidc_client_secret
        and settings.oauth_oidc_discovery_url
    ):
        from httpx_oauth.clients.openid import OpenID, OpenIDConfigurationError

        try:
            client = OpenID(
                settings.oauth_oidc_client_id,
                settings.oauth_oidc_client_secret,
                settings.oauth_oidc_discovery_url,
                name="oidc",
            )
        except OpenIDConfigurationError:
            logger.exception(
                "OIDC discovery failed for %s — provider disabled",
                settings.oauth_oidc_discovery_url,
            )
        else:
            out.append(
                OAuthProvider(
                    "oidc",
                    settings.oauth_oidc_display_name or "OIDC",
                    client,
                )
            )

    return out


def build_client_map(settings: UsersSettings) -> dict[str, OAuthProvider]:
    """Configured providers keyed by name for O(1) request-time lookup."""
    return {p.name: p for p in build_clients(settings)}


def provider_buttons(clients: dict[str, OAuthProvider]) -> list[dict[str, str]]:
    """Login-button descriptors derived from a built client map."""
    return [{"name": p.name, "display_name": p.display_name} for p in clients.values()]
