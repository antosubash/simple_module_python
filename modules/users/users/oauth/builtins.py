"""The bundled factories, shared by the app registry and standalone helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from users.core.oauth_settings import is_tenant_guid
from users.oauth.oidc_retry import OidcDiscovery
from users.oauth.providers import OAuthProvider

if TYPE_CHECKING:
    from httpx_oauth.oauth2 import BaseOAuth2

    from users.core.settings import UsersSettings

logger = logging.getLogger(__name__)


def _google(settings: UsersSettings) -> OAuthProvider | None:
    if not settings.oauth_google_client_id or not settings.oauth_google_client_secret:
        return None
    from users.oauth.google import GoogleWithNames

    return OAuthProvider(
        "google",
        "Google",
        GoogleWithNames(settings.oauth_google_client_id, settings.oauth_google_client_secret),
    )


def _github(settings: UsersSettings) -> OAuthProvider | None:
    if not settings.oauth_github_client_id or not settings.oauth_github_client_secret:
        return None
    from httpx_oauth.clients.github import GitHubOAuth2

    return OAuthProvider(
        "github",
        "GitHub",
        GitHubOAuth2(settings.oauth_github_client_id, settings.oauth_github_client_secret),
    )


def _microsoft(settings: UsersSettings) -> OAuthProvider | None:
    if not settings.oauth_microsoft_client_id or not settings.oauth_microsoft_client_secret:
        return None
    return OAuthProvider(
        "microsoft",
        "Microsoft",
        _microsoft_client(settings),
        trust_email=settings.oauth_microsoft_trust_tenant_upn
        and is_tenant_guid(settings.oauth_microsoft_tenant),
    )


def _oidc(settings: UsersSettings) -> OAuthProvider | None:
    if not (
        settings.oauth_oidc_client_id
        and settings.oauth_oidc_client_secret
        and settings.oauth_oidc_discovery_url
    ):
        return None
    from httpx_oauth.clients.openid import OpenID, OpenIDConfigurationError

    try:
        client: OpenID | OidcDiscovery = OpenID(
            settings.oauth_oidc_client_id,
            settings.oauth_oidc_client_secret,
            settings.oauth_oidc_discovery_url,
            name="oidc",
        )
    except (OpenIDConfigurationError, ValueError, KeyError, TypeError, IndexError):
        url = urlsplit(settings.oauth_oidc_discovery_url)
        safe_url = urlunsplit((url.scheme, url.netloc.rsplit("@", 1)[-1], url.path, "", ""))
        logger.warning(
            "OIDC discovery failed for %s — sign-in temporarily unavailable; "
            "retrying on demand with backoff",
            safe_url,
        )
        client = OidcDiscovery(settings)
    return OAuthProvider("oidc", settings.oauth_oidc_display_name or "OIDC", client)


def _microsoft_client(settings: UsersSettings) -> BaseOAuth2:
    """Entra's fixed endpoints, or a discovery override in development (#879)."""
    tenant = settings.oauth_microsoft_tenant or "common"
    discovery_url = settings.microsoft_discovery_url()
    if discovery_url:
        from users.oauth.microsoft_dev import MicrosoftDevOidc

        return MicrosoftDevOidc(
            settings.oauth_microsoft_client_id,
            settings.oauth_microsoft_client_secret,
            tenant,
            discovery_url,
        )
    from users.oauth.microsoft import MicrosoftOidc

    return MicrosoftOidc(
        settings.oauth_microsoft_client_id, settings.oauth_microsoft_client_secret, tenant
    )


BUILTIN_FACTORIES: dict[str, Callable[[UsersSettings], OAuthProvider | None]] = {
    "google": _google,
    "github": _github,
    "microsoft": _microsoft,
    "oidc": _oidc,
}


def build_builtin(name: str, settings: UsersSettings) -> OAuthProvider | None:
    """Apply the built-in domain trust policy without changing custom factories."""
    provider = BUILTIN_FACTORIES[name](settings)
    return (
        provider._replace(trusted_domains=settings.trusted_domains(name))
        if provider is not None
        else None
    )
